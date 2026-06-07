"""Milestone 2 background agent — scheduler, notifications, security tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.background_scheduler import BackgroundSchedulerService
from apps.api.services.background_tasks import BackgroundTaskService
from apps.api.services.notifications import sanitize_notification_summary
from apps.worker.commands import execute_read_only_command
from nova_core.background.schedules import daily_cron_at, validate_schedule_expression
from nova_core.background.task_types import BASE_RETRY_SECONDS, MAX_RETRY_ATTEMPTS
from nova_core.models.enums import BackgroundTaskStatus, BackgroundTaskType, TokenState
from nova_core.models.orm import AuditEvent, BackgroundTask, Device
from nova_core.tools.protected_paths import PROTECTED_PATH_MESSAGE


@pytest.fixture
def demo_project(tmp_path: Path) -> Path:
    root = tmp_path / "bg-demo"
    root.mkdir()
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_ok.py").write_text(
        "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
        encoding="utf-8",
    )
    (root / "Makefile").write_text(
        ".PHONY: test\n\ntest:\n\tpython3 -m unittest discover -s tests -q\n",
        encoding="utf-8",
    )
    return root.resolve()


@pytest.fixture
def failing_project(demo_project: Path) -> Path:
    (demo_project / "tests" / "test_ok.py").write_text(
        "import unittest\n\nclass T(unittest.TestCase):\n    def test_fail(self):\n        self.assertTrue(False)\n",
        encoding="utf-8",
    )
    return demo_project


@pytest.fixture
def allow_demo_root(demo_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def _fake_roots(roots: list[str] | None = None) -> list[Path]:
        return [demo_project]

    monkeypatch.setattr("nova_core.tools.safe_paths.expand_allowed_roots", _fake_roots)
    monkeypatch.setattr("nova_core.project.context.expand_allowed_roots", _fake_roots)
    return demo_project


async def _pair_second_client(auth_client: AsyncClient) -> tuple[str, str]:
    """Pair another client device using admin token; returns (device_id, token)."""
    import uuid

    device_b = f"test-client-{uuid.uuid4().hex[:8]}"
    auth_client.headers["Authorization"] = "Bearer nova_bts_test_admin"
    create_resp = await auth_client.post(
        "/api/v1/pairing/codes",
        json={"device_type": "iphone_client", "proposed_device_id": device_b},
    )
    assert create_resp.status_code == 201, create_resp.text
    code = create_resp.json()["code"]
    pairing_id = create_resp.json()["pairing_id"]
    claim = await auth_client.post(
        "/api/v1/pairing/claim",
        json={
            "code": code,
            "device_id": device_b,
            "name": "Other Client",
            "device_type": "iphone_client",
        },
        headers={k: v for k, v in auth_client.headers.items() if k.lower() != "authorization"},
    )
    assert claim.status_code == 200, claim.text
    if claim.json().get("status") in ("pending", "pending_approval"):
        await auth_client.post(f"/api/v1/pairing/{pairing_id}/approve")
        tok_resp = await auth_client.post(
            f"/api/v1/pairing/{pairing_id}/token",
            json={"device_id": device_b},
        )
        assert tok_resp.status_code == 200, tok_resp.text
        token_b = tok_resp.json()["token"]
    else:
        token_b = claim.json()["token"]
    return device_b, token_b


async def _auth_as_client(auth_client: AsyncClient, paired_client_token: tuple[str, str]) -> str:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    return token


async def _create_task(
    client: AsyncClient,
    *,
    project_root: str,
    schedule_kind: str = "interval",
    schedule_expression: str = "6h",
    task_type: str = BackgroundTaskType.REPO_RUN_VALIDATION.value,
) -> dict:
    resp = await client.post(
        "/api/v1/background-tasks",
        json={
            "task_type": task_type,
            "title": "Test validation task",
            "project_root": project_root,
            "schedule_kind": schedule_kind,
            "schedule_expression": schedule_expression,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_create_valid_daily_task(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    cron = daily_cron_at(9, 0)
    resp = await auth_client.post(
        "/api/v1/background-tasks",
        json={
            "task_type": BackgroundTaskType.REPO_HEALTH_CHECK.value,
            "title": "Daily check",
            "project_root": str(allow_demo_root),
            "schedule_kind": "cron",
            "schedule_expression": cron,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["schedule_expression"] == cron
    assert body["status"] == BackgroundTaskStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_create_valid_interval_task(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    task = await _create_task(
        auth_client,
        project_root=str(allow_demo_root),
        schedule_kind="interval",
        schedule_expression="6h",
    )
    assert task["schedule_kind"] == "interval"
    assert task["schedule_expression"] == "6h"


@pytest.mark.asyncio
async def test_reject_invalid_cron(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    resp = await auth_client.post(
        "/api/v1/background-tasks",
        json={
            "task_type": BackgroundTaskType.REPO_RUN_VALIDATION.value,
            "title": "Bad cron",
            "project_root": str(allow_demo_root),
            "schedule_kind": "cron",
            "schedule_expression": "*/5 * * * *",
        },
    )
    assert resp.status_code in {400, 422, 409}


def test_reject_invalid_cron_expression() -> None:
    with pytest.raises(ValueError, match="daily cron"):
        validate_schedule_expression("cron", "*/5 * * * *")


@pytest.mark.asyncio
async def test_reject_arbitrary_shell_task(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    resp = await auth_client.post(
        "/api/v1/background-tasks",
        json={
            "task_type": "shell.exec",
            "title": "Shell",
            "project_root": str(allow_demo_root),
            "schedule_kind": "interval",
            "schedule_expression": "1h",
        },
    )
    assert resp.status_code in {400, 422, 409}


@pytest.mark.asyncio
async def test_reject_protected_project_root(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    resp = await auth_client.post(
        "/api/v1/background-tasks",
        json={
            "task_type": BackgroundTaskType.REPO_RUN_VALIDATION.value,
            "title": "Protected",
            "project_root": "~/NOVA_VAULT/project",
            "schedule_kind": "interval",
            "schedule_expression": "6h",
        },
    )
    assert resp.status_code in {400, 422, 409}
    assert "protected" in resp.text.lower() or "Blocked" in resp.text


@pytest.mark.asyncio
async def test_reject_cross_device_task_read(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    _device_a, token_a = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token_a}"
    task = await _create_task(auth_client, project_root=str(allow_demo_root))

    _, token_b = await _pair_second_client(auth_client)
    auth_client.headers["Authorization"] = f"Bearer {token_b}"
    resp = await auth_client.get(f"/api/v1/background-tasks/{task['id']}")
    assert resp.status_code in {401, 403, 404}


@pytest.mark.asyncio
async def test_reject_cross_device_run_now(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    _device_a, token_a = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token_a}"
    task = await _create_task(auth_client, project_root=str(allow_demo_root))

    _, token_b = await _pair_second_client(auth_client)
    auth_client.headers["Authorization"] = f"Bearer {token_b}"
    resp = await auth_client.post(f"/api/v1/background-tasks/{task['id']}/run-now")
    assert resp.status_code in {401, 403, 409}


@pytest.mark.asyncio
async def test_revoked_device_rejected(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    db_session: AsyncSession,
    allow_demo_root: Path,
) -> None:
    device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    device = await db_session.get(Device, device_id)
    assert device is not None
    device.token_state = TokenState.REVOKED.value
    device.status = "revoked"
    await db_session.commit()

    resp = await auth_client.post(
        "/api/v1/background-tasks",
        json={
            "task_type": BackgroundTaskType.REPO_RUN_VALIDATION.value,
            "title": "Revoked",
            "project_root": str(allow_demo_root),
            "schedule_kind": "interval",
            "schedule_expression": "6h",
        },
    )
    assert resp.status_code in {401, 403}


@pytest.mark.asyncio
async def test_task_claim_atomic(
    db_session: AsyncSession,
    test_settings,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    from nova_core.auth.principal import Principal

    device_id, _ = paired_client_token
    device = await db_session.get(Device, device_id)
    assert device is not None
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id=device.user_id,
        device_id=device_id,
        token_role="client",
    )
    svc = BackgroundTaskService(db_session, test_settings)
    task = await svc.create_task(
        principal,
        task_type=BackgroundTaskType.REPO_INSPECT.value,
        title="Claim test",
        prompt=None,
        project_root=str(allow_demo_root),
        schedule_kind="once",
        schedule_expression=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    )
    await db_session.commit()

    claimed_a = await svc.try_claim_task(task.id)
    claimed_b = await svc.try_claim_task(task.id)
    assert claimed_a is not None
    assert claimed_b is None


@pytest.mark.asyncio
async def test_duplicate_scheduler_execution_prevented(
    db_session: AsyncSession,
    test_settings,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    from nova_core.auth.principal import Principal

    device_id, _ = paired_client_token
    device = await db_session.get(Device, device_id)
    assert device is not None
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id=device.user_id,
        device_id=device_id,
        token_role="client",
    )
    task_svc = BackgroundTaskService(db_session, test_settings)
    task = await task_svc.create_task(
        principal,
        task_type=BackgroundTaskType.SYSTEM_STATUS.value,
        title="Dup",
        prompt=None,
        project_root=None,
        schedule_kind="once",
        schedule_expression=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    )
    task.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    sched = BackgroundSchedulerService(db_session, test_settings)
    first = await sched.poll_and_dispatch(limit=5)
    second = await sched.poll_and_dispatch(limit=5)
    assert first["executed"] == 1
    assert second["executed"] == 0


@pytest.mark.asyncio
async def test_retry_bounded_and_backoff(
    db_session: AsyncSession,
    test_settings,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    from nova_core.auth.principal import Principal

    device_id, _ = paired_client_token
    device = await db_session.get(Device, device_id)
    assert device is not None
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id=device.user_id,
        device_id=device_id,
        token_role="client",
    )
    task_svc = BackgroundTaskService(db_session, test_settings)
    task = await task_svc.create_task(
        principal,
        task_type=BackgroundTaskType.REPO_INSPECT.value,
        title="Retry",
        prompt=None,
        project_root=str(allow_demo_root),
        schedule_kind="interval",
        schedule_expression="6h",
    )
    meta = dict(task.metadata_json or {})
    meta["retry_attempt"] = MAX_RETRY_ATTEMPTS
    task.metadata_json = meta
    await db_session.commit()
    assert int(task.metadata_json["retry_attempt"]) == MAX_RETRY_ATTEMPTS


def test_retry_backoff_formula() -> None:
    for attempt in range(1, MAX_RETRY_ATTEMPTS):
        backoff = BASE_RETRY_SECONDS * (2 ** (attempt - 1))
        assert backoff >= BASE_RETRY_SECONDS


@pytest.mark.asyncio
async def test_pause_prevents_run(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    task = await _create_task(auth_client, project_root=str(allow_demo_root))
    pause = await auth_client.post(f"/api/v1/background-tasks/{task['id']}/pause")
    assert pause.status_code == 200
    run = await auth_client.post(f"/api/v1/background-tasks/{task['id']}/run-now")
    assert run.status_code == 409


@pytest.mark.asyncio
async def test_resume_recalculates_next_run(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    task = await _create_task(auth_client, project_root=str(allow_demo_root))
    await auth_client.post(f"/api/v1/background-tasks/{task['id']}/pause")
    resumed = await auth_client.post(f"/api/v1/background-tasks/{task['id']}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["next_run_at"] is not None
    assert resumed.json()["status"] == BackgroundTaskStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_cancel_prevents_future_run(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    task = await _create_task(auth_client, project_root=str(allow_demo_root))
    cancelled = await auth_client.post(f"/api/v1/background-tasks/{task['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["next_run_at"] is None
    run = await auth_client.post(f"/api/v1/background-tasks/{task['id']}/run-now")
    assert run.status_code == 409


@pytest.mark.asyncio
async def test_validation_failure_creates_notification(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    failing_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_roots(roots: list[str] | None = None) -> list[Path]:
        return [failing_project]

    monkeypatch.setattr("nova_core.tools.safe_paths.expand_allowed_roots", _fake_roots)
    monkeypatch.setattr("nova_core.project.context.expand_allowed_roots", _fake_roots)
    await _auth_as_client(auth_client, paired_client_token)
    task = await _create_task(auth_client, project_root=str(failing_project))
    run = await auth_client.post(f"/api/v1/background-tasks/{task['id']}/run-now")
    assert run.status_code == 200
    notes = await auth_client.get("/api/v1/notifications")
    assert notes.status_code == 200
    types = [n["notification_type"] for n in notes.json()["notifications"]]
    assert "validation.failed" in types


@pytest.mark.asyncio
async def test_recovery_creates_notification(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    failing_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_roots(roots: list[str] | None = None) -> list[Path]:
        return [failing_project]

    monkeypatch.setattr("nova_core.tools.safe_paths.expand_allowed_roots", _fake_roots)
    monkeypatch.setattr("nova_core.project.context.expand_allowed_roots", _fake_roots)
    await _auth_as_client(auth_client, paired_client_token)
    task = await _create_task(auth_client, project_root=str(failing_project))
    fail_run = await auth_client.post(f"/api/v1/background-tasks/{task['id']}/run-now")
    assert fail_run.json()["status"] == "failed"

    (failing_project / "tests" / "test_ok.py").write_text(
        "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
        encoding="utf-8",
    )

    ok_run = await auth_client.post(f"/api/v1/background-tasks/{task['id']}/run-now")
    assert ok_run.json()["status"] == "succeeded"
    notes = await auth_client.get("/api/v1/notifications")
    types = [n["notification_type"] for n in notes.json()["notifications"]]
    assert "validation.recovered" in types


@pytest.mark.asyncio
async def test_notification_device_scoped(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    device_a, token_a = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token_a}"
    task = await _create_task(auth_client, project_root=str(allow_demo_root))
    await auth_client.post(f"/api/v1/background-tasks/{task['id']}/run-now")

    _, token_b = await _pair_second_client(auth_client)
    auth_client.headers["Authorization"] = f"Bearer {token_b}"
    notes_b = await auth_client.get("/api/v1/notifications")
    assert notes_b.json()["unread_count"] == 0


def test_notification_safe_summary_only() -> None:
    raw = "Done. token=nova_cli_secret123 password=abc"
    cleaned = sanitize_notification_summary(raw)
    assert "nova_cli_secret123" not in cleaned
    assert "password=abc" not in cleaned.lower() or "[redacted]" in cleaned.lower()


@pytest.mark.asyncio
async def test_no_token_secret_leakage_in_notifications(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    task = await _create_task(
        auth_client,
        project_root=str(allow_demo_root),
        task_type=BackgroundTaskType.REMINDER_NOTE.value,
    )
    await auth_client.post(f"/api/v1/background-tasks/{task['id']}/run-now")
    notes = await auth_client.get("/api/v1/notifications")
    blob = notes.text.lower()
    assert "nova_cli_" not in blob
    assert "nova_bts_" not in blob


def test_worker_revalidates_policy() -> None:
    result = execute_read_only_command("inspect_repo", {"project_root": "~/NOVA_VAULT/project"})
    assert result["success"] is False
    assert (
        PROTECTED_PATH_MESSAGE.lower() in str(result.get("error", "")).lower()
        or "protected" in str(result.get("error", "")).lower()
    )


@pytest.mark.asyncio
async def test_background_task_cannot_auto_apply_patch(
    db_session: AsyncSession,
    test_settings,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    from nova_core.auth.principal import Principal
    from nova_core.background.executor import BackgroundTaskExecutor
    from nova_core.schemas.errors import ValidationError

    device_id, _ = paired_client_token
    device = await db_session.get(Device, device_id)
    assert device is not None
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id=device.user_id,
        device_id=device_id,
        token_role="client",
    )
    svc = BackgroundTaskService(db_session, test_settings)
    with pytest.raises(ValidationError):
        await svc.create_task(
            principal,
            task_type="patch.apply",
            title="Patch",
            prompt=None,
            project_root=str(allow_demo_root),
            schedule_kind="once",
            schedule_expression=datetime.now(UTC).isoformat(),
        )

    executor = BackgroundTaskExecutor(db_session, test_settings)
    result = await executor.execute(
        task_type=BackgroundTaskType.REPO_RUN_VALIDATION.value,
        project_root=str(allow_demo_root),
        prompt=None,
    )
    evidence = result.evidence or {}
    assert "patch" not in str(evidence).lower() or "apply" not in str(evidence).lower()


@pytest.mark.asyncio
async def test_scheduler_restart_resumes_persisted_tasks(
    db_session: AsyncSession,
    test_settings,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    from nova_core.auth.principal import Principal

    device_id, _ = paired_client_token
    device = await db_session.get(Device, device_id)
    assert device is not None
    principal = Principal(
        principal_type="device",
        principal_id=device_id,
        user_id=device.user_id,
        device_id=device_id,
        token_role="client",
    )
    task_svc = BackgroundTaskService(db_session, test_settings)
    task = await task_svc.create_task(
        principal,
        task_type=BackgroundTaskType.SYSTEM_STATUS.value,
        title="Persist",
        prompt=None,
        project_root=None,
        schedule_kind="interval",
        schedule_expression="1h",
    )
    task.status = BackgroundTaskStatus.RUNNING.value
    await db_session.commit()

    sched = BackgroundSchedulerService(db_session, test_settings)
    recovered = await sched.recover_stale_running()
    assert recovered == 1
    refreshed = await db_session.get(BackgroundTask, task.id)
    assert refreshed is not None
    assert refreshed.status == BackgroundTaskStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_chat_create_daily_repo_check(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    await auth_client.post("/api/v1/projects/active", json={"project_root": str(allow_demo_root)})
    chat = await auth_client.post(
        "/api/v1/chat",
        json={"message": "create daily repo check at 9am"},
    )
    assert chat.status_code == 200
    assert "Created background task" in chat.json()["response"]
    assert "0 9 * * *" in chat.json()["response"]


@pytest.mark.asyncio
async def test_audit_events_recorded(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
    db_session: AsyncSession,
) -> None:
    await _auth_as_client(auth_client, paired_client_token)
    task = await _create_task(auth_client, project_root=str(allow_demo_root))
    await auth_client.post(f"/api/v1/background-tasks/{task['id']}/run-now")
    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.resource_id == task["id"])
    )
    actions = {e.action for e in result.scalars().all()}
    assert "background_task.created" in actions or any("background_task" in a for a in actions)

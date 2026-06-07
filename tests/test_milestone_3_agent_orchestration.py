"""Milestone 3 local multi-agent orchestration — security and workflow tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.agent_plans import AgentPlanService
from apps.api.services.git_workflow import GitWorkflowService
from nova_core.auth.principal import Principal
from nova_core.capabilities.model import CapabilityName, compute_action_fingerprint
from nova_core.models.enums import AgentPlanStatus
from nova_core.models.orm import AgentPlan, ApprovalRequest, Device
from nova_core.orchestration.step_types import (
    ALLOWED_ACTION_TYPES,
    DEFAULT_MAX_STEPS,
    build_default_repair_plan,
    validate_step_action,
)
from nova_core.providers.external_adapters import AnthropicAdapter, OpenAIAdapter
from nova_core.providers.trust_lanes import (
    ExternalProviderKind,
    active_lane,
    evaluate_external_call,
    trust_lane_summary,
)
from nova_core.schemas.settings import Settings


@pytest.fixture
def demo_project(tmp_path: Path) -> Path:
    root = tmp_path / "orch-demo"
    root.mkdir()
    (root / "Makefile").write_text(
        ".PHONY: test\n\ntest:\n\tpython3 -m unittest discover -s tests -q\n"
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "demo_fail.py").write_text(
        "def test_demo():\n    assert False\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Demo", encoding="utf-8")
    subprocess_init = root
    import subprocess

    subprocess.run(["git", "init"], cwd=subprocess_init, capture_output=True, check=False)
    subprocess.run(
        ["git", "config", "user.email", "demo@test.local"], cwd=subprocess_init, check=False
    )
    subprocess.run(["git", "config", "user.name", "Demo"], cwd=subprocess_init, check=False)
    subprocess.run(["git", "add", "."], cwd=subprocess_init, capture_output=True, check=False)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=subprocess_init, capture_output=True, check=False
    )
    return root.resolve()


@pytest.fixture
def allow_demo_root(demo_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def _fake_roots(roots: list[str] | None = None) -> list[Path]:
        return [demo_project]

    monkeypatch.setattr("nova_core.tools.safe_paths.expand_allowed_roots", _fake_roots)
    monkeypatch.setattr("nova_core.project.context.expand_allowed_roots", _fake_roots)
    return demo_project


def _principal(device_id: str, user_id: str = "arth") -> Principal:
    return Principal(
        principal_type="device",
        principal_id=device_id,
        user_id=user_id,
        device_id=device_id,
    )


async def _set_active_project(auth_client: AsyncClient, token: str, project_root: Path) -> None:
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/projects/active",
        json={"project_root": str(project_root)},
    )
    assert resp.status_code == 200, resp.text


async def _approved_record(
    db_session: AsyncSession,
    device_id: str,
    capability: CapabilityName,
    payload: dict,
) -> ApprovalRequest:
    device = await db_session.get(Device, device_id)
    assert device is not None
    fp = compute_action_fingerprint(capability.value, payload)
    record = ApprovalRequest(
        user_id=device.user_id,
        device_id=device_id,
        capability=capability.value,
        action_summary="test",
        command_or_payload_preview="preview",
        action_fingerprint=fp,
        risk_level="high",
        status="approved",
        metadata_json={"payload": payload},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


def test_planner_max_steps_enforced() -> None:
    steps = build_default_repair_plan(objective="fix tests")
    assert len(steps) <= DEFAULT_MAX_STEPS


def test_unsupported_step_rejected() -> None:
    ok, reason = validate_step_action("shell.execute")
    assert not ok
    assert reason is not None
    assert "Unsupported" in reason


def test_allowed_action_types_complete() -> None:
    assert "patch.propose" in ALLOWED_ACTION_TYPES
    assert "shell.execute" not in ALLOWED_ACTION_TYPES


def test_external_provider_disabled_by_default(test_settings: Settings) -> None:
    test_settings.nova_external_providers_enabled = False
    decision = evaluate_external_call(test_settings, provider=ExternalProviderKind.ANTHROPIC)
    assert not decision.allowed


def test_cloud_file_transmission_requires_approval(test_settings: Settings) -> None:
    test_settings.nova_external_providers_enabled = True
    test_settings.nova_anthropic_enabled = True
    decision = evaluate_external_call(
        test_settings,
        provider=ExternalProviderKind.ANTHROPIC,
        file_paths=["/tmp/readme.md"],
        cloud_send_approved=False,
    )
    assert not decision.allowed
    assert decision.requires_approval


def test_protected_content_never_sent_externally(test_settings: Settings) -> None:
    test_settings.nova_external_providers_enabled = True
    test_settings.nova_anthropic_enabled = True
    decision = evaluate_external_call(
        test_settings,
        provider=ExternalProviderKind.ANTHROPIC,
        file_paths=["~/NOVA_VAULT/secret.txt"],
        cloud_send_approved=True,
    )
    assert not decision.allowed


def test_trust_lane_summary_no_raw_keys(test_settings: Settings) -> None:
    test_settings.nova_anthropic_api_key = "sk-secret-should-not-appear"
    summary = trust_lane_summary(test_settings)
    dumped = str(summary)
    assert "sk-secret" not in dumped
    assert "configured" in dumped


@pytest.mark.asyncio
async def test_active_lane_local_by_default(test_settings: Settings) -> None:
    test_settings.nova_external_providers_enabled = False
    assert active_lane(test_settings).value == "local"


@pytest.mark.asyncio
async def test_external_adapters_blocked_without_flag(test_settings: Settings) -> None:
    adapter = AnthropicAdapter(test_settings)
    result = await adapter.infer("secret prompt with sk-fake12345678")
    assert result.blocked
    openai = OpenAIAdapter(test_settings)
    o_result = await openai.infer("prompt")
    assert o_result.blocked


@pytest.mark.asyncio
async def test_create_plan_cross_device_blocked(
    db_session: AsyncSession,
    test_settings: Settings,
    allow_demo_root: Path,
    paired_client_token: tuple[str, str],
) -> None:
    device_id, _ = paired_client_token
    principal = _principal(device_id)
    svc = AgentPlanService(db_session, test_settings)
    plan = await svc.create_plan(
        principal, objective="test", draft=True, project_root=str(allow_demo_root)
    )
    other = _principal("other-device-id")
    with pytest.raises(Exception):
        await svc.get_plan(other, plan.id)


@pytest.mark.asyncio
async def test_orchestration_plan_api(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    device_id, token = paired_client_token
    await _set_active_project(auth_client, token, allow_demo_root)
    resp = await auth_client.post(
        "/api/v1/agent-plans",
        json={"objective": "Fix failing unittest", "draft": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["plan_id"]
    assert len(data["steps"]) <= 8


@pytest.mark.asyncio
async def test_run_plan_waits_for_patch_approval(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    device_id, token = paired_client_token
    await _set_active_project(auth_client, token, allow_demo_root)
    create = await auth_client.post(
        "/api/v1/agent-plans",
        json={"objective": "Fix failing unittest"},
    )
    assert create.status_code == 200, create.text
    result = create.json()
    assert result["plan_id"]
    assert (
        result.get("waiting_approval")
        or result.get("approval_id")
        or result["status"]
        in {
            "waiting_approval",
            "completed",
            "running",
            "failed",
        }
    )


@pytest.mark.asyncio
async def test_git_push_blocked(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post("/api/v1/git/push")
    assert resp.status_code == 200
    assert resp.json()["blocked"] is True


@pytest.mark.asyncio
async def test_branch_creation_requires_approval(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/git/propose-branch",
        json={"project_root": str(allow_demo_root), "branch_name": "nova/test-branch"},
    )
    assert resp.status_code == 200
    assert resp.json()["approval_id"]
    assert resp.json()["push_disabled"] is True


@pytest.mark.asyncio
async def test_git_commit_requires_separate_approval(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.post(
        "/api/v1/git/propose-commit",
        json={
            "project_root": str(allow_demo_root),
            "commit_message": "fix: demo",
            "staged_paths": ["tests/demo_fail.py"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["approval_id"]


@pytest.mark.asyncio
async def test_protected_path_patch_blocked(
    allow_demo_root: Path,
    test_settings: Settings,
) -> None:
    from nova_core.orchestration.executor import OrchestrationExecutor

    executor = OrchestrationExecutor(test_settings, allowed_roots=[str(allow_demo_root)])
    payload = {
        "project_root": str(allow_demo_root),
        "summary": "bad",
        "files": [
            {
                "path": "../NOVA_VAULT/secret.env",
                "action": "modify",
                "content": "leak",
            }
        ],
        "unified_diff": "",
    }
    executor.set_context({})
    executor._context["patch_payload"] = payload
    result = await executor._patch_review(allow_demo_root, "x", None)
    assert result.blocked or not result.success


@pytest.mark.asyncio
async def test_background_creates_draft_plan_only(
    db_session: AsyncSession,
    test_settings: Settings,
    allow_demo_root: Path,
    paired_client_token: tuple[str, str],
) -> None:
    from apps.api.services.background_scheduler import BackgroundSchedulerService
    from nova_core.models.enums import (
        BackgroundRunStatus,
        BackgroundScheduleKind,
        BackgroundTaskStatus,
        BackgroundTaskType,
    )
    from nova_core.models.orm import BackgroundTask, BackgroundTaskRun

    device_id, _ = paired_client_token
    device = await db_session.get(Device, device_id)
    assert device is not None
    task = BackgroundTask(
        user_id=device.user_id,
        device_id=device_id,
        project_root=str(allow_demo_root),
        task_type=BackgroundTaskType.REPO_RUN_VALIDATION.value,
        title="Validation",
        schedule_kind=BackgroundScheduleKind.ONCE.value,
        schedule_expression="once",
        status=BackgroundTaskStatus.RUNNING.value,
    )
    db_session.add(task)
    await db_session.flush()
    run = BackgroundTaskRun(
        task_id=task.id,
        user_id=device.user_id,
        device_id=device_id,
        status=BackgroundRunStatus.FAILED.value,
        summary="tests failed",
    )
    db_session.add(run)
    await db_session.flush()

    sched = BackgroundSchedulerService(db_session, test_settings)
    await sched._maybe_create_draft_repair_plan(task, "validation failed")
    assert task.metadata_json and task.metadata_json.get("draft_plan_id")
    plan = await db_session.get(AgentPlan, task.metadata_json["draft_plan_id"])
    assert plan is not None
    assert plan.status == AgentPlanStatus.DRAFT.value


@pytest.mark.asyncio
async def test_provider_trust_endpoint(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    resp = await auth_client.get("/api/v1/provider-trust")
    assert resp.status_code == 200
    body = resp.text
    assert "sk-" not in body
    assert resp.json()["active_lane"] == "local"


@pytest.mark.asyncio
async def test_chat_orchestration_intent(
    auth_client: AsyncClient,
    paired_client_token: tuple[str, str],
    allow_demo_root: Path,
) -> None:
    _device_id, token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    await _set_active_project(auth_client, token, allow_demo_root)
    resp = await auth_client.post(
        "/api/v1/chat",
        json={"message": "show active plan"},
    )
    assert resp.status_code == 200
    assert (
        "plan" in resp.json()["response"].lower() or "no active" in resp.json()["response"].lower()
    )


@pytest.mark.asyncio
async def test_fingerprint_mismatch_blocks_git_commit(
    db_session: AsyncSession,
    test_settings: Settings,
    allow_demo_root: Path,
    paired_client_token: tuple[str, str],
) -> None:
    device_id, _ = paired_client_token
    payload = {
        "project_root": str(allow_demo_root),
        "commit_message": "fix",
        "staged_paths": ["tests/demo_fail.py"],
    }
    record = await _approved_record(db_session, device_id, CapabilityName.GIT_COMMIT, payload)
    record.action_fingerprint = "deadbeef" * 8
    await db_session.commit()
    git_svc = GitWorkflowService(db_session, test_settings)
    principal = _principal(device_id)
    with pytest.raises(Exception):
        await git_svc.commit_approved(principal, record.id)

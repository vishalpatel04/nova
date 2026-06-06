"""Worker command dispatch — Redis Streams transport and recovery tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.services.worker_dispatch import WorkerDispatchService
from nova_core.models.enums import WorkerCommandStatus
from nova_core.models.orm import Mission, WorkerCommandAssignment
from nova_core.worker_dispatch.streams import class_stream_key, read_commands


@pytest.mark.asyncio
async def test_command_stream_append(fake_redis) -> None:
    from nova_core.worker_dispatch.streams import write_command

    entry = await write_command(
        fake_redis,
        class_stream_key("macos_worker"),
        command_id="cmd-test-1",
        command_type="hostname",
        mission_id=None,
    )
    assert entry is not None
    replay = await read_commands(fake_redis, class_stream_key("macos_worker"))
    assert replay[0]["command_id"] == "cmd-test-1"


@pytest.mark.asyncio
async def test_worker_offline_mission_queues_command(
    auth_client: AsyncClient, paired_client_token, db_engine, test_settings
) -> None:
    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    resp = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Dispatch queue"},
        headers={"Idempotency-Key": "dispatch-queue-1"},
    )
    mission_id = resp.json()["id"]
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            select(WorkerCommandAssignment).where(WorkerCommandAssignment.mission_id == mission_id)
        )
        assignment = result.scalar_one()
        assert assignment.status in (
            WorkerCommandStatus.DISPATCHED.value,
            WorkerCommandStatus.PENDING.value,
        )


@pytest.mark.asyncio
async def test_worker_reconnect_receives_assignment_once(
    auth_client: AsyncClient,
    paired_worker_token,
    paired_client_token,
    db_engine,
    test_settings,
) -> None:
    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Reconnect once"},
        headers={"Idempotency-Key": "dispatch-reconnect-1"},
    )
    device_id, _token = paired_worker_token

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        dispatch = WorkerDispatchService(session, test_settings)
        first = await dispatch.pending_commands_for_worker(device_id, "macos_worker")
        second = await dispatch.pending_commands_for_worker(device_id, "macos_worker")
        assert len(first) == 1
        assert first == second
        command_id = first[0]["command_id"]
        await dispatch.acknowledge_pickup(device_id=device_id, command_id=command_id)
        third = await dispatch.pending_commands_for_worker(device_id, "macos_worker")
        assert third == []


@pytest.mark.asyncio
async def test_duplicate_pickup_and_result_idempotent(
    auth_client: AsyncClient, paired_worker_token, paired_client_token, db_engine, test_settings
) -> None:
    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Idempotent dispatch"},
        headers={"Idempotency-Key": "dispatch-idem-1"},
    )
    device_id, _token = paired_worker_token

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        dispatch = WorkerDispatchService(session, test_settings)
        commands = await dispatch.pending_commands_for_worker(device_id, "macos_worker")
        command_id = commands[0]["command_id"]
        await dispatch.acknowledge_pickup(device_id=device_id, command_id=command_id)
        await dispatch.acknowledge_pickup(device_id=device_id, command_id=command_id)
        result_payload = {"hostname": "test-host", "status": "ok"}
        await dispatch.record_result(
            device_id=device_id,
            command_id=command_id,
            success=True,
            result_payload=result_payload,
        )
        await dispatch.record_result(
            device_id=device_id,
            command_id=command_id,
            success=True,
            result_payload=result_payload,
        )
        row = await session.execute(
            select(WorkerCommandAssignment).where(WorkerCommandAssignment.command_id == command_id)
        )
        assignment = row.scalar_one()
        assert assignment.status == WorkerCommandStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_offline_worker_reconnect_lifecycle_completes_from_result(
    auth_client: AsyncClient,
    paired_worker_token,
    paired_client_token,
    db_engine,
    test_settings,
) -> None:
    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    resp = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Offline worker lifecycle"},
        headers={"Idempotency-Key": "dispatch-lifecycle-1"},
    )
    assert resp.status_code == 201
    mission_id = resp.json()["id"]
    assert resp.json()["status"] == "queued_waiting_for_worker"

    device_id, _token = paired_worker_token
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        dispatch = WorkerDispatchService(session, test_settings)
        commands = await dispatch.pending_commands_for_worker(device_id, "macos_worker")
        assert len(commands) == 1
        command_id = commands[0]["command_id"]

        await dispatch.acknowledge_pickup(device_id=device_id, command_id=command_id)
        mission_row = await session.execute(select(Mission).where(Mission.id == mission_id))
        mission = mission_row.scalar_one()
        assert mission.status == "running"

        result_payload = {
            "hostname": "test-host",
            "os_version": "test-os",
            "architecture": "arm64",
            "status": "ok",
        }
        await dispatch.record_result(
            device_id=device_id,
            command_id=command_id,
            success=True,
            result_payload=result_payload,
        )
        await dispatch.record_result(
            device_id=device_id,
            command_id=command_id,
            success=True,
            result_payload=result_payload,
        )

        row = await session.execute(
            select(WorkerCommandAssignment).where(WorkerCommandAssignment.command_id == command_id)
        )
        assignment = row.scalar_one()
        assert assignment.status == WorkerCommandStatus.COMPLETED.value
        assert assignment.result_payload == result_payload

        mission_row = await session.execute(select(Mission).where(Mission.id == mission_id))
        mission = mission_row.scalar_one()
        assert mission.status == "completed"
        assert mission.result_payload == result_payload


@pytest.mark.asyncio
async def test_api_restart_assignment_survives(
    db_engine, test_settings, paired_client_token
) -> None:
    from apps.api.services.missions import MissionService
    from nova_core.models.orm import Mission, User

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        user = User(id="user-restart", display_name="Restart User")
        session.add(user)
        mission = Mission(
            user_id=user.id,
            mission_type="system_status",
            title="Restart survival",
            assigned_agent_id="nova",
            status="queued_waiting_for_worker",
        )
        session.add(mission)
        await session.flush()
        mission_svc = MissionService(session, test_settings)
        await mission_svc._queue_mission(mission)
        result = await session.execute(
            select(WorkerCommandAssignment).where(WorkerCommandAssignment.mission_id == mission.id)
        )
        assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_stale_assignment_recovery(db_engine, test_settings) -> None:
    from datetime import timedelta

    from nova_core.models.orm import WorkerCommandAssignment
    from nova_core.utils.time import utc_now

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        assignment = WorkerCommandAssignment(
            command_id="stale-cmd-1",
            command_type="hostname",
            routing_mode="worker_class",
            target_worker_class="macos_worker",
            status=WorkerCommandStatus.DISPATCHED.value,
            dispatched_at=utc_now() - timedelta(seconds=600),
            attempt_count=1,
            max_attempts=3,
        )
        session.add(assignment)
        await session.commit()

        dispatch = WorkerDispatchService(session, test_settings)
        recovered = await dispatch.recover_stale_assignments()
        assert "stale-cmd-1" in recovered
        await session.refresh(assignment)
        assert assignment.status == WorkerCommandStatus.PENDING.value


@pytest.mark.asyncio
async def test_revoked_worker_cannot_pickup(
    auth_client: AsyncClient, paired_worker_token, paired_client_token, db_engine, test_settings
) -> None:
    from nova_core.schemas.errors import ConflictError

    device_id, _token = paired_worker_token
    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Revoked worker"},
        headers={"Idempotency-Key": "dispatch-revoked-1"},
    )

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        dispatch = WorkerDispatchService(session, test_settings)
        commands = await dispatch.pending_commands_for_worker(device_id, "macos_worker")
        command_id = commands[0]["command_id"]

    auth_client.headers["Authorization"] = "Bearer nova_bts_test_admin"
    await auth_client.post(f"/api/v1/devices/{device_id}/revoke", json={"reason": "test"})

    async with factory() as session:
        dispatch = WorkerDispatchService(session, test_settings)
        pending = await dispatch.pending_commands_for_worker(device_id, "macos_worker")
        assert pending == []
        with pytest.raises(ConflictError):
            await dispatch.acknowledge_pickup(device_id=device_id, command_id=command_id)


@pytest.mark.asyncio
async def test_worker_class_routing_two_workers(
    db_engine, test_settings, paired_worker_token
) -> None:
    from nova_core.models.orm import Mission, User

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        user = User(id="user-class-route", display_name="Class Route")
        mission = Mission(
            user_id=user.id,
            mission_type="system_status",
            title="Class route",
            assigned_agent_id="nova",
            status="queued_waiting_for_worker",
        )
        session.add(user)
        session.add(mission)
        await session.flush()
        dispatch = WorkerDispatchService(session, test_settings)
        assignment = await dispatch.create_mission_command(
            mission_id=mission.id,
            mission_type="system_status",
            required_device_types=["macos_worker"],
        )
        worker_a, _ = paired_worker_token
        worker_b = "other-worker-id"
        first = await dispatch.pending_commands_for_worker(worker_a, "macos_worker")
        assert first[0]["command_id"] == assignment.command_id
        second = await dispatch.pending_commands_for_worker(worker_b, "macos_worker")
        assert second == []
        await session.commit()


@pytest.mark.asyncio
async def test_device_specific_routing(db_engine, test_settings) -> None:
    from nova_core.models.orm import Mission, User

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        user = User(id="user-device-route", display_name="Device Route")
        mission = Mission(
            user_id=user.id,
            mission_type="system_status",
            title="Device route",
            assigned_agent_id="nova",
            status="queued_waiting_for_worker",
        )
        session.add(user)
        session.add(mission)
        await session.flush()
        dispatch = WorkerDispatchService(session, test_settings)
        assignment = await dispatch.create_mission_command(
            mission_id=mission.id,
            mission_type="system_status",
            target_device_id="only-this-worker",
        )
        await dispatch.dispatch_assignment(assignment)
        match = await dispatch.pending_commands_for_worker("only-this-worker", "macos_worker")
        other = await dispatch.pending_commands_for_worker("other-worker", "macos_worker")
        assert len(match) == 1
        assert other == []
        await session.commit()


def test_read_only_command_handlers() -> None:
    from apps.worker.commands import execute_read_only_command

    hostname = execute_read_only_command("hostname")
    assert "hostname" in hostname
    caps = execute_read_only_command("configured_capabilities")
    assert "capabilities" in caps

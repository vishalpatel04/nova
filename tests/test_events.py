"""Slice 2A event streaming and timeline tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_timeline_has_sequence_numbers(
    auth_client: AsyncClient, paired_worker_token, paired_client_token
) -> None:
    _device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"

    await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": _device_id, "status": "online"},
    )
    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"

    mission_resp = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Timeline test"},
        headers={"Idempotency-Key": "timeline-seq-1"},
    )
    assert mission_resp.status_code == 201
    mission_id = mission_resp.json()["id"]

    timeline = await auth_client.get(f"/api/v1/missions/{mission_id}/timeline")
    assert timeline.status_code == 200
    events = timeline.json()["events"]
    assert len(events) >= 1
    sequences = [e["sequence_number"] for e in events if e["sequence_number"]]
    assert sequences == sorted(sequences)
    assert timeline.json()["streaming"] in ("live", "degraded")


@pytest.mark.asyncio
async def test_postgresql_timeline_durability(
    auth_client: AsyncClient, paired_worker_token, paired_client_token
) -> None:
    _device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": _device_id, "status": "online"},
    )
    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"

    mission_resp = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Durability test"},
    )
    mission_id = mission_resp.json()["id"]

    detail = await auth_client.get(f"/api/v1/missions/{mission_id}")
    assert len(detail.json()["timeline_events"]) >= 1


@pytest.mark.asyncio
async def test_streaming_status_degraded_without_redis(client: AsyncClient) -> None:
    client.headers["Authorization"] = "Bearer nova_bts_test_admin"
    resp = await client.get("/api/v1/system/streaming-status")
    assert resp.status_code == 200
    assert resp.json()["streaming"] in ("degraded", "live")


@pytest.mark.asyncio
async def test_redis_stream_append_and_replay(db_session, fake_redis, test_settings) -> None:
    from nova_core.events.publisher import publish_timeline_event, read_stream_events
    from nova_core.models.orm import Mission, User

    user = User(id="user-stream", display_name="Stream User")
    mission = Mission(
        id="mission-stream-1",
        user_id=user.id,
        mission_type="system_status",
        title="Stream test",
        assigned_agent_id="nova",
        status="pending",
    )
    db_session.add(user)
    db_session.add(mission)
    await db_session.flush()

    published = await publish_timeline_event(
        db_session,
        fake_redis,
        mission_id=mission.id,
        event_type="mission.created",
        agent_id="nova",
        message="First event",
        payload={"n": 1},
    )
    assert published.streaming == "live"
    assert published.stream_id is not None

    replay = await read_stream_events(fake_redis, mission.id, after_sequence=0)
    assert len(replay) == 1
    assert replay[0]["sequence_number"] == published.sequence_number

    published2 = await publish_timeline_event(
        db_session,
        fake_redis,
        mission_id=mission.id,
        event_type="mission.progress",
        agent_id="nova",
        message="Second event",
    )
    replay_after = await read_stream_events(
        fake_redis, mission.id, after_sequence=published.sequence_number
    )
    assert len(replay_after) == 1
    assert replay_after[0]["sequence_number"] == published2.sequence_number


@pytest.mark.asyncio
async def test_timeline_replay_after_sequence(
    auth_client: AsyncClient, paired_worker_token, paired_client_token
) -> None:
    device_id, token = paired_worker_token
    auth_client.headers["Authorization"] = f"Bearer {token}"
    await auth_client.post(
        "/api/v1/workers/heartbeat",
        json={"device_id": device_id, "status": "online"},
    )
    _client_id, client_token = paired_client_token
    auth_client.headers["Authorization"] = f"Bearer {client_token}"
    mission = await auth_client.post(
        "/api/v1/missions",
        json={"mission_type": "system_status", "title": "Replay test"},
    )
    mission_id = mission.json()["id"]

    full = await auth_client.get(f"/api/v1/missions/{mission_id}/timeline")
    events = full.json()["events"]
    assert len(events) >= 1
    last_seq = max(e["sequence_number"] for e in events if e["sequence_number"])

    replay = await auth_client.get(
        f"/api/v1/missions/{mission_id}/timeline",
        params={"after_sequence": last_seq},
    )
    assert replay.json()["after_sequence"] == last_seq
    assert all(e["sequence_number"] > last_seq for e in replay.json()["events"])

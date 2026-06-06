"""Connected worker registry for live WebSocket workers."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ConnectedWorker:
    device_id: str
    device_type: str
    connected_at: datetime
    last_heartbeat: datetime
    capabilities: list[str] = field(default_factory=list)
    status_payload: dict[str, Any] = field(default_factory=dict)


class WorkerConnectionManager:
    def __init__(self) -> None:
        self._workers: dict[str, ConnectedWorker] = {}

    def register(
        self, device_id: str, device_type: str, capabilities: list[str] | None = None
    ) -> None:
        now = datetime.now(UTC)
        self._workers[device_id] = ConnectedWorker(
            device_id=device_id,
            device_type=device_type,
            connected_at=now,
            last_heartbeat=now,
            capabilities=capabilities or [],
        )

    def heartbeat(self, device_id: str, payload: dict[str, Any] | None = None) -> None:
        worker = self._workers.get(device_id)
        if worker:
            worker.last_heartbeat = datetime.now(UTC)
            if payload:
                worker.status_payload = payload

    def disconnect(self, device_id: str) -> None:
        self._workers.pop(device_id, None)

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._workers

    def has_eligible_worker(self) -> bool:
        eligible = {"macos_worker", "linux_worker", "cloud_worker"}
        return any(w.device_type in eligible for w in self._workers.values())

    def list_connected(self) -> list[ConnectedWorker]:
        return list(self._workers.values())

    def get(self, device_id: str) -> ConnectedWorker | None:
        return self._workers.get(device_id)

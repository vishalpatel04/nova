"""Worker control-plane WebSocket client."""

import asyncio
import json
import platform
import random
import time
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from apps.worker.capabilities import capability_report, detect_capabilities
from nova_core.schemas.settings import WorkerSettings
from nova_core.sentry.logging import get_logger

logger = get_logger("nova.worker.ws")


class WorkerWebSocketClient:
    def __init__(self, settings: WorkerSettings, device_id: str, device_name: str) -> None:
        self.settings = settings
        self.device_id = device_id
        self.device_name = device_name
        self._ws: ClientConnection | None = None
        self._running = False
        self._reconnect_delay = 1.0
        self.connection_status = "disconnected"
        self.last_heartbeat: float | None = None
        self.started_at = time.time()

    @property
    def ws_url(self) -> str:
        base = self.settings.control_plane_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        token = self.settings.worker_token
        return f"{base}/api/v1/ws/worker?token={token}"

    def status_report(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "hostname": platform.node(),
            "os_version": platform.platform(),
            "architecture": platform.machine(),
            "uptime_seconds": int(time.time() - self.started_at),
            "capabilities": detect_capabilities(),
            "connection_status": self.connection_status,
            "last_heartbeat": self.last_heartbeat,
            "dangerous_tools_enabled": False,
        }

    async def connect(self) -> None:
        self.connection_status = "reconnecting"
        self._ws = await websockets.connect(self.ws_url)
        self.connection_status = "connected"
        self._reconnect_delay = 1.0
        logger.info("worker_ws_connected", device_id=self.device_id)

        await self._send(
            {
                "type": "register",
                "name": self.device_name,
                "device_type": self.settings.device_type,
                "device_id": self.device_id,
                "hostname": platform.node(),
                "os_version": platform.platform(),
                "architecture": platform.machine(),
                "capabilities": detect_capabilities(),
                "metadata": capability_report(),
            }
        )

    async def _send(self, msg: dict[str, Any]) -> None:
        if self._ws:
            await self._ws.send(json.dumps(msg))

    async def heartbeat_loop(self) -> None:
        while self._running:
            try:
                if self._ws is None:
                    await self.connect()
                report = self.status_report()
                await self._send({"type": "heartbeat", "payload": report})
                self.last_heartbeat = time.time()
            except Exception as exc:
                logger.warning("worker_ws_heartbeat_failed", error=str(exc))
                self.connection_status = "reconnecting"
                self._ws = None
                delay = self._reconnect_delay + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60.0)
                continue

            await asyncio.sleep(self.settings.worker_heartbeat_interval_seconds)

    async def listen_loop(self) -> None:
        while self._running:
            try:
                if self._ws is None:
                    await asyncio.sleep(0.5)
                    continue
                raw = await self._ws.recv()
                msg = json.loads(raw)
                logger.info("worker_ws_message", type=msg.get("type"))
            except Exception:
                self._ws = None
                self.connection_status = "reconnecting"

    async def run(self) -> None:
        self._running = True
        await asyncio.gather(self.heartbeat_loop(), self.listen_loop())

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
        self.connection_status = "disconnected"

"""Worker control-plane WebSocket client."""

import asyncio
import json
import platform
import random
import time
from typing import Any

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

from apps.worker.capabilities import capability_report, detect_capabilities
from apps.worker.commands import execute_read_only_command
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
        self._handled_commands: set[str] = set()

    async def _fetch_ws_ticket(self) -> str:
        url = f"{self.settings.control_plane_url}/api/v1/pairing/ws-tickets"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {self.settings.resolved_worker_token}"},
                json={"scope": "worker"},
            )
            response.raise_for_status()
            data: dict[str, str] = response.json()
            return data["ticket"]

    @property
    async def ws_url(self) -> str:
        base = self.settings.control_plane_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        ticket = await self._fetch_ws_ticket()
        return f"{base}/api/v1/ws/worker?ticket={ticket}"

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
        url = await self.ws_url
        self._ws = await websockets.connect(url)
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

    async def _handle_command(self, cmd: dict[str, str]) -> None:
        command_id = cmd.get("command_id", "")
        if not command_id or command_id in self._handled_commands:
            return
        command_type = cmd.get("command_type", "")
        await self._send({"type": "command_pickup_ack", "command_id": command_id})
        try:
            result = execute_read_only_command(command_type)
            await self._send(
                {
                    "type": "command_result",
                    "command_id": command_id,
                    "success": True,
                    "result": result,
                }
            )
            self._handled_commands.add(command_id)
        except Exception as exc:
            await self._send(
                {
                    "type": "command_result",
                    "command_id": command_id,
                    "success": False,
                    "error": str(exc),
                }
            )

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        msg_type = msg.get("type")
        if msg_type == "commands_assigned":
            for cmd in msg.get("commands", []):
                await self._handle_command(cmd)
        elif msg_type == "missions_assigned":
            for item in msg.get("assignments", []):
                mission_id = item.get("mission_id")
                command_id = item.get("command_id")
                if mission_id and command_id:
                    await self._send(
                        {
                            "type": "mission_pickup_ack",
                            "mission_id": mission_id,
                            "command_id": command_id,
                        }
                    )

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
                await self._handle_message(msg)
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

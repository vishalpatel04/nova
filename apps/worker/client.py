"""Control plane API client for worker registration and heartbeat."""

import platform
from typing import Any

import httpx

from nova_core.schemas.settings import WorkerSettings
from nova_core.sentry.logging import get_logger

logger = get_logger("nova.worker.client")


class ControlPlaneClient:
    def __init__(self, settings: WorkerSettings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.control_plane_url,
            headers={"Authorization": f"Bearer {settings.nova_api_token}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def register(
        self,
        *,
        device_id: str,
        name: str,
        device_type: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "device_id": device_id,
            "name": name,
            "device_type": device_type,
            "hostname": platform.node(),
            "os_version": platform.platform(),
            "capabilities": capabilities,
            "metadata": metadata or {},
        }
        response = await self._client.post("/api/v1/workers/register", json=payload)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        logger.info("registered", device_id=device_id)
        return result

    async def heartbeat(
        self,
        *,
        device_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = {
            "device_id": device_id,
            "status": "online",
            "payload": payload or {},
        }
        response = await self._client.post("/api/v1/workers/heartbeat", json=body)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def health_check(self) -> bool:
        try:
            response = await self._client.get("/api/v1/health")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

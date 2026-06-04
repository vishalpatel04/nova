"""Worker daemon main entry point."""

import asyncio
import signal
import uuid
from typing import Any

import uvicorn
from fastapi import FastAPI

from apps.worker.capabilities import capability_report, detect_capabilities
from apps.worker.client import ControlPlaneClient
from apps.worker.ws_client import WorkerWebSocketClient
from nova_core.schemas.settings import WorkerSettings, get_worker_settings
from nova_core.sentry.logging import configure_logging, get_logger

logger = get_logger("nova.worker")


class WorkerDaemon:
    def __init__(self, settings: WorkerSettings) -> None:
        self.settings = settings
        self.client = ControlPlaneClient(settings)
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._ws_task: asyncio.Task[None] | None = None
        self._reconnect_delay = 1.0
        self._device_id = settings.device_id or f"worker-{uuid.uuid4().hex[:12]}"
        self._ws_client: WorkerWebSocketClient | None = None

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def device_name(self) -> str:
        if self.settings.device_name:
            return self.settings.device_name
        import platform

        return f"{platform.node()}-worker"

    async def start(self) -> None:
        self._running = True
        if self.settings.worker_ws_enabled and self.settings.resolved_worker_token:
            self._ws_client = WorkerWebSocketClient(self.settings, self.device_id, self.device_name)
            self._ws_task = asyncio.create_task(self._ws_client.run())
            logger.info("worker_ws_mode", device_id=self.device_id)
        else:
            await self._register_with_retry()
            self._task = asyncio.create_task(self._heartbeat_loop())
            logger.info("worker_rest_mode", device_id=self.device_id)

    async def stop(self) -> None:
        self._running = False
        if self._ws_client:
            await self._ws_client.stop()
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.client.close()
        logger.info("worker_stopped", device_id=self.device_id)

    async def _register_with_retry(self) -> None:
        while self._running:
            try:
                caps = detect_capabilities()
                await self.client.register(
                    device_id=self.device_id,
                    name=self.device_name,
                    device_type=self.settings.device_type,
                    capabilities=caps,
                    metadata=capability_report(),
                )
                self._reconnect_delay = 1.0
                return
            except Exception as exc:
                logger.warning("register_failed", error=str(exc), retry_in=self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60.0)

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                report = capability_report()
                await self.client.heartbeat(
                    device_id=self.device_id,
                    payload=report,
                )
                self._reconnect_delay = 1.0
            except Exception as exc:
                logger.warning("heartbeat_failed", error=str(exc))
                await self._register_with_retry()

            await asyncio.sleep(self.settings.worker_heartbeat_interval_seconds)


_worker: WorkerDaemon | None = None


def create_health_app() -> FastAPI:
    app = FastAPI(title="NOVA Worker Health")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        settings = get_worker_settings()
        ws = _worker._ws_client if _worker else None
        return {
            "status": "ok" if _worker and _worker._running else "starting",
            "device_id": _worker.device_id if _worker else settings.device_id or "unassigned",
            "device_type": settings.device_type,
            "connection_status": ws.connection_status if ws else "rest",
            "status_report": ws.status_report() if ws else {},
        }

    return app


async def run_worker() -> None:
    global _worker
    settings = get_worker_settings()
    configure_logging("INFO")

    _worker = WorkerDaemon(settings)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(_worker.stop()))

    health_app = create_health_app()
    config = uvicorn.Config(
        health_app,
        host="0.0.0.0",
        port=settings.worker_health_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    await _worker.start()

    try:
        await server.serve()
    finally:
        await _worker.stop()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()

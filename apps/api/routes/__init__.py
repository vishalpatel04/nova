"""API route modules."""

from apps.api.routes.chat import router as chat_router
from apps.api.routes.core import router as core_router
from apps.api.routes.pairing import devices_router
from apps.api.routes.pairing import router as pairing_router
from apps.api.routes.runtime import router as runtime_router
from apps.api.routes.scheduler import router as scheduler_router
from apps.api.routes.timeline import router as timeline_router
from apps.api.routes.worker_ws import router as worker_ws_router

__all__ = [
    "chat_router",
    "core_router",
    "pairing_router",
    "runtime_router",
    "scheduler_router",
    "devices_router",
    "timeline_router",
    "worker_ws_router",
]

"""API route modules."""

from apps.api.routes.core import router as core_router
from apps.api.routes.pairing import devices_router
from apps.api.routes.pairing import router as pairing_router
from apps.api.routes.timeline import router as timeline_router
from apps.api.routes.worker_ws import router as worker_ws_router

__all__ = [
    "core_router",
    "pairing_router",
    "devices_router",
    "timeline_router",
    "worker_ws_router",
]

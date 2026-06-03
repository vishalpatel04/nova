"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.deps import AppState, set_app_state
from apps.api.routes import router
from apps.api.services.seed import seed_agents
from nova_core import __version__
from nova_core.models.database import dispose_db, get_session, init_db
from nova_core.schemas.errors import NovaError
from nova_core.schemas.settings import Settings, get_settings
from nova_core.sentry.logging import configure_logging, get_logger

logger = get_logger("nova.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.nova_log_level)

    logger.info("starting", version=__version__, env=settings.nova_env)

    init_db(settings)

    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info("redis_connected")
    except Exception as exc:
        logger.warning("redis_unavailable", error=str(exc))

    state = AppState(settings=settings, redis=redis_client)
    set_app_state(state)

    try:
        async for session in get_session():
            count = await seed_agents(session, settings)
            logger.info("agents_seeded", count=count)
            break
    except Exception as exc:
        logger.warning("seed_failed", error=str(exc))

    _validate_startup(settings)

    yield

    if redis_client:
        await redis_client.aclose()
    await dispose_db()
    logger.info("shutdown_complete")


def _validate_startup(settings: Settings) -> None:
    required_configs = [
        "agents.yaml",
        "models.yaml",
        "voices.yaml",
        "devices.yaml",
        "policies.yaml",
    ]
    for cfg in required_configs:
        settings.load_yaml(cfg)
    logger.info("startup_validation_passed")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings:
        from nova_core.schemas.settings import get_settings

        get_settings.cache_clear()

    app = FastAPI(
        title="NOVA Control Plane",
        version=__version__,
        lifespan=lifespan,
    )

    @app.exception_handler(NovaError)
    async def nova_error_handler(_request: Request, exc: NovaError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    app.include_router(router, prefix="/api/v1")
    return app


app = create_app()

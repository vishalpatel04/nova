"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.deps import AppState, set_app_state
from apps.api.routes import (
    agent_os_router,
    agent_plans_router,
    approvals_router,
    background_tasks_router,
    chat_router,
    core_router,
    devices_router,
    executions_router,
    memory_router,
    pairing_router,
    projects_router,
    runtime_router,
    scheduler_router,
    timeline_router,
    worker_ws_router,
)
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

    scheduler_task: asyncio.Task[None] | None = None
    memory_task: asyncio.Task[None] | None = None
    if settings.nova_env != "test":
        scheduler_task = asyncio.create_task(_background_scheduler_loop(settings))
        memory_task = asyncio.create_task(_background_memory_compiler_loop(settings))

    yield

    if memory_task is not None:
        memory_task.cancel()
        with suppress(asyncio.CancelledError):
            await memory_task

    if scheduler_task is not None:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task

    if redis_client:
        await redis_client.aclose()
    await dispose_db()
    logger.info("shutdown_complete")


async def _background_scheduler_loop(settings: Settings) -> None:
    from apps.api.services.background_scheduler import BackgroundSchedulerService
    from nova_core.models.database import get_session

    poll_seconds = BackgroundSchedulerService.POLL_INTERVAL_SECONDS
    logger.info("background_scheduler_started", poll_seconds=poll_seconds)
    while True:
        try:
            async for session in get_session():
                sched = BackgroundSchedulerService(session, settings)
                await sched.recover_stale_running()
                await sched.poll_and_dispatch()
                await session.commit()
                break
        except asyncio.CancelledError:
            logger.info("background_scheduler_stopped")
            raise
        except Exception as exc:
            logger.warning("background_scheduler_tick_failed", error=str(exc))
        await asyncio.sleep(poll_seconds)


async def _background_memory_compiler_loop(settings: Settings) -> None:
    from apps.api.services.memory_compiler_loop import memory_compiler_tick
    from nova_core.models.database import get_session

    poll_seconds = 45
    logger.info("memory_compiler_started", poll_seconds=poll_seconds)
    while True:
        try:
            async for session in get_session():
                await memory_compiler_tick(session, settings)
                await session.commit()
                break
        except asyncio.CancelledError:
            logger.info("memory_compiler_stopped")
            raise
        except Exception as exc:
            logger.warning("memory_compiler_tick_failed", error=str(exc))
        await asyncio.sleep(poll_seconds)


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
    if settings.nova_env not in {"development", "test"}:
        if settings.nova_token_pepper == "dev-pepper-change-in-production":
            raise RuntimeError("NOVA_TOKEN_PEPPER must be set outside development/test")
        if (
            settings.nova_bootstrap_admin_enabled
            and settings.nova_bootstrap_admin_token == "nova_bts_dev_bootstrap"
        ):
            raise RuntimeError(
                "NOVA_BOOTSTRAP_ADMIN_TOKEN must be changed outside development/test"
            )
    logger.info("startup_validation_passed")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings:
        from nova_core.schemas.settings import get_settings

        get_settings.cache_clear()

    app = FastAPI(
        title="NOVA Control Plane",
        version=__version__,
        description=(
            "NOVA personal AI operating system — authenticated control plane "
            "with durable mission events"
        ),
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

    app.include_router(core_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")
    app.include_router(executions_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(memory_router, prefix="/api/v1")
    app.include_router(agent_os_router, prefix="/api/v1")
    app.include_router(background_tasks_router, prefix="/api/v1")
    app.include_router(agent_plans_router, prefix="/api/v1")
    app.include_router(pairing_router, prefix="/api/v1")
    app.include_router(runtime_router, prefix="/api/v1")
    app.include_router(scheduler_router, prefix="/api/v1")
    app.include_router(devices_router, prefix="/api/v1")
    app.include_router(timeline_router, prefix="/api/v1")
    app.include_router(worker_ws_router, prefix="/api/v1")
    return app


app = create_app()

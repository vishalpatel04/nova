"""Resolve Alembic database URL from environment with safe inspection helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from alembic.config import Config
from sqlalchemy.engine.url import make_url


class DatabaseUrlConfigurationError(RuntimeError):
    """Raised when neither DATABASE_URL nor alembic.ini provides a database URL."""


@dataclass(frozen=True)
class DatabaseUrlEndpoint:
    host: str
    port: int
    database: str


def resolve_database_url(
    *,
    env_database_url: str | None,
    config_database_url: str | None,
) -> str:
    """Prefer DATABASE_URL from the environment; fall back to alembic.ini for local dev."""
    env_value = (env_database_url or "").strip()
    if env_value:
        return env_value

    config_value = (config_database_url or "").strip()
    if config_value:
        return config_value

    raise DatabaseUrlConfigurationError(
        "DATABASE_URL is not set and alembic.ini sqlalchemy.url is empty. "
        "Export DATABASE_URL or configure sqlalchemy.url for local development."
    )


def configure_alembic_database_url(config: Config) -> str:
    """Apply resolved database URL to Alembic config without logging credentials."""
    url = resolve_database_url(
        env_database_url=os.environ.get("DATABASE_URL"),
        config_database_url=config.get_main_option("sqlalchemy.url"),
    )
    config.set_main_option("sqlalchemy.url", url)
    return url


def inspect_database_url(url: str) -> DatabaseUrlEndpoint:
    """Return host/port/database only — never username or password."""
    parsed = make_url(url)
    host = parsed.host or "localhost"
    port = parsed.port or 5432
    database = parsed.database or ""
    return DatabaseUrlEndpoint(host=host, port=port, database=database)


def sanitize_database_url_repr(url: str) -> str:
    """Safe host:port/database label for tests and diagnostics."""
    endpoint = inspect_database_url(url)
    return f"{endpoint.host}:{endpoint.port}/{endpoint.database}"

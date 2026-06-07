"""Resolve Alembic database URL from environment with safe inspection helpers."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from alembic.config import Config
from sqlalchemy.engine.url import make_url

from nova_core.schemas.settings import Settings, _is_shell_localhost_database_url


@dataclass(frozen=True)
class DatabaseUrlEndpoint:
    host: str
    port: int
    database: str


def load_repo_database_url() -> str:
    """Load the repository-local database URL from the canonical .env path."""
    return Settings().database_url.strip()


def resolve_database_url(
    *,
    env_database_url: str | None,
    repo_database_url: str | None,
    config_database_url: str | None,
) -> str:
    """Prefer explicit DATABASE_URL, then repo .env, then safe local fallback."""
    env_value = (env_database_url or "").strip()
    override_allowed = os.environ.get("NOVA_ALLOW_DATABASE_URL_OVERRIDE") == "1"
    if override_allowed and env_value:
        return env_value
    if env_value and not _is_shell_localhost_database_url(env_value):
        return env_value

    repo_value = (repo_database_url or "").strip()
    if repo_value:
        return repo_value

    config_value = (config_database_url or "").strip()
    if config_value:
        return config_value

    return "postgresql+asyncpg://nova:nova@localhost:5433/nova"


def configure_alembic_database_url(config: Config) -> str:
    """Apply resolved database URL to Alembic config without logging credentials."""
    url = resolve_database_url(
        env_database_url=os.environ.get("DATABASE_URL"),
        repo_database_url=load_repo_database_url(),
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


def print_database_target(url: str) -> None:
    endpoint = inspect_database_url(url)
    print(f"host={endpoint.host}")
    print(f"port={endpoint.port}")
    print(f"database={endpoint.database}")


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    url = resolve_database_url(
        env_database_url=os.environ.get("DATABASE_URL"),
        repo_database_url=load_repo_database_url(),
        config_database_url=None,
    )
    print_database_target(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

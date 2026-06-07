"""Tests for Alembic DATABASE_URL resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config

from infra.migrations.database_url import (
    configure_alembic_database_url,
    inspect_database_url,
    resolve_database_url,
    sanitize_database_url_repr,
)
from nova_core.schemas.settings import Settings, get_settings

ROOT = Path(__file__).resolve().parents[1]
ENV_DATABASE_URL = "postgresql+asyncpg://override:secret@db.example.com:5433/nova_test"
INI_FALLBACK_URL = "postgresql+asyncpg://nova:nova@localhost:5433/nova"


def test_database_url_environment_override_wins_over_alembic_ini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", ENV_DATABASE_URL)
    cfg = Config(str(ROOT / "alembic.ini"))
    resolved = configure_alembic_database_url(cfg)
    assert resolved == ENV_DATABASE_URL
    assert cfg.get_main_option("sqlalchemy.url") == ENV_DATABASE_URL


def test_database_url_falls_back_to_alembic_ini_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = Config(str(ROOT / "alembic.ini"))
    resolved = configure_alembic_database_url(cfg)
    assert resolved == INI_FALLBACK_URL
    assert ":5433/" in resolved


def test_alembic_ini_default_points_to_docker_port() -> None:
    ini_text = (ROOT / "alembic.ini").read_text(encoding="utf-8")
    assert "localhost:5433/nova" in ini_text
    assert "localhost:5432/nova" not in ini_text


def test_settings_default_database_url_points_to_docker_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    settings = Settings()
    assert settings.database_url == INI_FALLBACK_URL
    get_settings.cache_clear()


def test_sanitize_database_url_does_not_expose_credentials() -> None:
    url = "postgresql+asyncpg://nova:nova@localhost:5433/nova"
    endpoint = inspect_database_url(url)
    safe = sanitize_database_url_repr(url)

    assert endpoint.host == "localhost"
    assert endpoint.port == 5433
    assert endpoint.database == "nova"
    assert "nova:" not in safe
    assert "@" not in safe
    assert safe == "localhost:5433/nova"


def test_resolve_database_url_requires_explicit_source_when_both_missing() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        resolve_database_url(env_database_url=None, config_database_url=None)

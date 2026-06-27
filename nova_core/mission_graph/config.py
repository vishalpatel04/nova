"""MissionGraph run configuration."""

from __future__ import annotations

from dataclasses import dataclass

from nova_core.schemas.settings import Settings


@dataclass(frozen=True)
class MissionGraphRunConfig:
    selected_engine: str = "deterministic_template"
    settings: Settings | None = None
    run_npm: bool = True
    start_preview: bool = True
    clean_workspace: bool = False
    allow_fallback: bool = False

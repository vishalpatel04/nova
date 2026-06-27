"""Forge engine orchestration service."""

from __future__ import annotations

from pathlib import Path

from nova_core.forge.engines.base import ForgeTask
from nova_core.forge.engines.deterministic_template import DeterministicTemplateEngine
from nova_core.forge.engines.registry import default_engine_id, get_engine, list_engines
from nova_core.forge.execution import default_constraints
from nova_core.forge.selector import suggest_forge_engine
from nova_core.schemas.settings import Settings


class ForgeEngineService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def engines_status(self) -> list[dict[str, str | bool | list[str]]]:
        rows: list[dict[str, str | bool | list[str]]] = []
        for engine in list_engines(self.settings):
            rows.append(
                {
                    "engine_id": engine.engine_id,
                    "display_name": engine.display_name,
                    "available": engine.available(),
                    "setup_hint": engine.setup_hint(),
                    "capabilities": engine.capabilities(),
                }
            )
        return rows

    def suggest(self, request: str) -> dict[str, object]:
        return suggest_forge_engine(request).to_dict()

    def run(
        self,
        request: str,
        *,
        project_path: Path | None = None,
        engine_id: str | None = None,
    ) -> dict[str, object]:
        engine_key = engine_id or default_engine_id(self.settings)
        engine = get_engine(engine_key, self.settings)
        fallback = DeterministicTemplateEngine()
        if engine is None:
            engine = fallback
            engine_key = fallback.engine_id
        constraints = default_constraints(project_path)
        task = ForgeTask(request=request)
        executed = engine
        if engine.available():
            result = engine.run_task(task, constraints.workspace, constraints)
        else:
            hint = engine.setup_hint()
            result = fallback.run_task(task, constraints.workspace, constraints)
            result.summary = f"{hint}\n\nFallback: {result.summary}"
            result.fallback_used = True
            engine_key = fallback.engine_id
            executed = fallback
        validation = executed.run_validation(constraints.workspace, constraints)
        return {
            "engine_id": engine_key,
            "result": result.to_dict(),
            "validation": validation.to_dict(),
            "suggestion": self.suggest(request),
        }

"""External agent stack adapter tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from apps.api.services.forge_engine_service import ForgeEngineService
from nova_core.forge.engines.base import ForgeConstraints, ForgeTask
from nova_core.forge.engines.registry import get_engine, list_engines
from nova_core.forge.execution import redact_prompt_text, write_engine_prompt
from nova_core.forge.selector import suggest_forge_engine
from nova_core.gateway.router import GatewayRouter
from nova_core.mission_graph.runner import MissionGraphRunner
from nova_core.mission_graph.store import MissionGraphStore
from nova_core.models.lanes import lane_statuses, recommend_lanes
from nova_core.orchestration.app_builder import BuildResult, CommandResult
from nova_core.schemas.settings import Settings
from nova_core.voice.openwakeword_adapter import status as ow_status
from nova_core.voice.pipeline import route_voice_transcript


@pytest.fixture
def workspace_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "nova-workspace"
    root.mkdir()
    monkeypatch.setenv("NOVA_WORKSPACE_ROOT", str(root))
    return root


def test_audit_doc_exists() -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / "EXTERNAL_AGENT_STACK_AUDIT.md"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    for name in ("OpenHands", "LangGraph", "OpenClaw", "openWakeWord"):
        assert name in text


def test_mission_graph_records_nodes(tmp_path: Path) -> None:
    runner = MissionGraphRunner(store=MissionGraphStore(base_dir=tmp_path / "graphs"))
    state = runner.create_state("mid-1", "build a landing page for SusCo")
    evidence = runner.run(state)
    assert len(evidence.nodes) == 11
    assert evidence.nodes[0]["node_id"] == "classify_request"
    assert evidence.engine_selected


def test_deterministic_template_available() -> None:
    engine = get_engine("deterministic_template")
    assert engine is not None
    assert engine.available()


def test_openhands_unavailable_hint() -> None:
    engine = get_engine("openhands")
    assert engine is not None
    if not engine.available():
        assert "OpenHands" in engine.setup_hint()


def test_claude_unavailable_hint() -> None:
    engine = get_engine("claude_code_cli")
    assert engine is not None
    if not engine.available():
        assert "Claude" in engine.setup_hint()


def test_codex_unavailable_hint() -> None:
    engine = get_engine("codex_cli")
    assert engine is not None
    if not engine.available():
        assert "Codex" in engine.setup_hint()


def test_forge_workspace_scoped(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    constraints = ForgeConstraints(workspace=ws)
    from nova_core.forge.execution import is_path_allowed

    assert is_path_allowed(ws, constraints)
    assert not is_path_allowed(outside, constraints)


def test_prompt_redacts_secrets(tmp_path: Path) -> None:
    task = ForgeTask(request="build app", app_spec_summary="api_key=sk-secret1234567890")
    constraints = ForgeConstraints(workspace=tmp_path)
    path = write_engine_prompt(tmp_path, engine_id="test", task=task, constraints=constraints)
    body = path.read_text(encoding="utf-8")
    assert "sk-secret" not in body
    assert redact_prompt_text(
        "token=abc123"
    ) != "token=abc123" or "[REDACTED]" in redact_prompt_text("api_key=sk-test12345678901234567890")


def test_openclaw_no_skill_execution() -> None:
    router = GatewayRouter()
    stance = router.openclaw_reference_only()
    assert stance["skill_execution"] == "disabled"


def test_openwakeword_setup_hint() -> None:
    st = ow_status()
    assert st.setup_hint
    if not st.available:
        assert "pip install" in st.setup_hint.lower() or "openwakeword" in st.setup_hint.lower()


def test_voice_simulation_routes() -> None:
    cmd, wake = route_voice_transcript("hey nova build a todo app called voice tasks")
    assert wake
    assert "todo" in cmd.lower()


def test_model_lanes() -> None:
    rows = lane_statuses(Settings())
    assert len(rows) >= 4
    rec = recommend_lanes(Settings())
    assert "local_fast" in rec


def test_complex_app_suggests_external() -> None:
    suggestion = suggest_forge_engine("build expense tracker with login and database")
    assert suggestion.suggest_external
    assert suggestion.complexity == "complex"


def test_forge_service_fallback(workspace_tmp: Path) -> None:
    build = BuildResult(
        project_path=str(workspace_tmp / "ext-demo-calculator-app"),
        files_written=[str(workspace_tmp / "ext-demo-calculator-app" / "package.json")],
        install=CommandResult("npm install", str(workspace_tmp), 0, "", "", True),
        build=CommandResult("npm run build", str(workspace_tmp), 0, "", "", True),
        preview=None,
        preview_url=None,
        build_passed=True,
        app_type="calculator",
        app_name="ext-demo",
        template_id="calculator_v1",
    )
    with (
        patch("nova_core.forge.engines.deterministic_template.build_app", return_value=build),
        patch("nova_core.forge.execution.run_safe_command", return_value=(0, "ok", "")),
    ):
        svc = ForgeEngineService(Settings())
        out = svc.run("build a calculator app named ext-demo", engine_id="openhands")
    assert out["engine_id"] in {e.engine_id for e in list_engines()}
    assert "result" in out

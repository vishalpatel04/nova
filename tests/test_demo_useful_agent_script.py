"""Regression tests for scripts/demo_useful_agent.sh safe-root isolation."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_useful_agent.sh"


def test_demo_script_does_not_use_symlink_or_tmp_project_root() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "ln -s" not in text
    assert "symlink" not in lowered
    assert "/tmp/nova-demo" not in text
    assert 'mktemp -d "$safe_root/milestone-demo' in text or (
        'mktemp -d "$SAFE_ROOT/milestone-demo' in text
    )
    assert "NOVA-Safe-Test" in text
    assert "sanitize_api_error" in text
    assert "NOVA_DEMO_DEBUG" in text
    assert "pytest" not in text
    assert "unittest discover" in text


def test_demo_script_cleanup_only_removes_safe_root_demo_dir() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"$SAFE_ROOT"/milestone-demo-*' in text
    assert 'rm -rf "$DEMO_DIR"' in text

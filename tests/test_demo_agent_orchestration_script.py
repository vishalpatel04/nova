"""Regression tests for scripts/demo_agent_orchestration.sh auth and pairing."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_agent_orchestration.sh"


def test_script_has_no_stdin_device_id_dead_code_hang() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "open('$ROOT/.demo-device-id'" not in text
    assert "if False else sys.stdin" not in text
    assert 'device_id="m3-demo-$$"' in text


def test_script_uses_nova_demo_token_env() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'TOKEN="${NOVA_DEMO_TOKEN:-}"' in text


def test_paired_token_skips_pairing_endpoints() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "authenticate_client()" in text
    assert 'if [[ -n "$TOKEN" ]]; then' in text
    assert "GET /api/v1/runtime/status" in text
    # Pairing only after empty-token branch requires admin
    pairing_block = text.split('if [[ -n "$TOKEN" ]]; then', 1)[1]
    assert "/api/v1/pairing/codes" in pairing_block
    assert "return 0" in pairing_block.split("/api/v1/pairing/codes", 1)[0]


def test_missing_credentials_fails_cleanly() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "NOVA_DEMO_TOKEN (paired client) or NOVA_ADMIN_TOKEN" in text
    assert "exit 1" in text

    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": "/tmp",
        "NOVA_API_URL": "http://127.0.0.1:1",
        "NOVA_DEMO_TOKEN": "",
        "NOVA_ADMIN_TOKEN": "",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        check=False,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "NOVA_DEMO_TOKEN" in combined or "NOVA_ADMIN_TOKEN" in combined


def test_no_hardcoded_bootstrap_token_fallback() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "nova_bts_dev_bootstrap" not in text
    assert 'ADMIN_TOKEN="${NOVA_ADMIN_TOKEN:-}"' in text


def test_api_helper_has_curl_timeouts() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--connect-timeout 3" in text
    assert "--max-time 15" in text


def test_script_never_echoes_token_values() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'echo "$TOKEN"' not in text
    assert "echo $TOKEN" not in text
    assert "not printed" in text
    assert "sanitize_api_error" in text

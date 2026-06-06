"""macOS Keychain helpers for local worker credentials."""

from __future__ import annotations

import platform
import subprocess


def read_generic_password(service: str, account: str) -> str | None:
    if platform.system() != "Darwin":
        return None
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return None
    password = result.stdout.strip()
    return password or None

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


def write_generic_password(service: str, account: str, secret: str) -> bool:
    if platform.system() != "Darwin":
        return False
    subprocess.run(
        ["security", "delete-generic-password", "-s", service, "-a", account],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
            secret,
            "-U",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode == 0


def delete_generic_password(service: str, account: str) -> bool:
    if platform.system() != "Darwin":
        return False
    result = subprocess.run(
        ["security", "delete-generic-password", "-s", service, "-a", account],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode == 0

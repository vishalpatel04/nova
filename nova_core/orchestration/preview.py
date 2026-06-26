"""Preview server lifecycle for generated apps."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from nova_core.agent_os.workspace import assert_workspace_write


@dataclass
class PreviewSession:
    pid: int
    port: int
    url: str
    log_path: str
    reachable: bool


def find_free_port(start: int = 5173, max_tries: int = 10) -> int:
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free preview port in range {start}-{start + max_tries - 1}")


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def wait_for_preview(url: str, *, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                body = response.read(800).lower()
                if response.status == 200 and (b"<html" in body or b"<!doctype" in body):
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.5)
    return False


def start_preview_server(project_path: Path, *, port: int, log_path: Path) -> subprocess.Popen[str]:
    root = assert_workspace_write(project_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(root),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def launch_preview(
    project_path: Path,
    *,
    preferred_port: int = 5173,
    log_dir: Path | None = None,
) -> PreviewSession:
    root = assert_workspace_write(project_path)
    port = (
        preferred_port if is_port_available(preferred_port) else find_free_port(preferred_port + 1)
    )
    logs = log_dir or (root / ".nova-preview")
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"preview-{port}.log"
    proc = start_preview_server(root, port=port, log_path=log_path)
    url = f"http://127.0.0.1:{port}"
    reachable = wait_for_preview(url)
    return PreviewSession(
        pid=proc.pid,
        port=port,
        url=url,
        log_path=str(log_path),
        reachable=reachable,
    )


def stop_preview(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.killpg(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            return False
    except PermissionError:
        return False

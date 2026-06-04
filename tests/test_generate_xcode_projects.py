"""Regression tests for Xcode project generation."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.generate_xcode_projects import (
    collect_swift_files,
    generate_macos_pbxproj,
    generate_pbxproj,
    is_valid_swift_source,
    pbx_path_literal,
)

ROOT = Path(__file__).resolve().parent.parent
PBX_PATH_RE = re.compile(r'path = ("(?:\\.|[^"\\])*"|[^;]+);')


def _parse_pbx_source_paths(pbx_content: str) -> list[str]:
    paths: list[str] = []
    for match in PBX_PATH_RE.finditer(pbx_content):
        raw = match.group(1).strip()
        if raw.startswith('"'):
            paths.append(json.loads(raw))
        else:
            paths.append(raw)
    return paths


def _swift_source_paths_from_pbx(pbx_content: str) -> list[str]:
    return [
        p
        for p in _parse_pbx_source_paths(pbx_content)
        if p.endswith(".swift") and "/" in p or p.endswith(".swift") and not p.endswith(".xctest")
    ]


def test_pbx_path_literal_quotes_spaces() -> None:
    assert (
        pbx_path_literal(Path("Networking/Mac Timeline.swift")) == '"Networking/Mac Timeline.swift"'
    )


def test_rejects_whitespace_only_swift_stem(tmp_path: Path) -> None:
    bad = tmp_path / "Networking"
    bad.mkdir()
    (bad / "\u00a0\u00a0.swift").write_text("// bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid Swift source"):
        collect_swift_files(tmp_path)


def test_macos_generated_paths_resolve_to_files() -> None:
    app_dir = ROOT / "apps" / "macos" / "NOVA"
    pbx = generate_macos_pbxproj(
        "NOVAGenie", app_dir, "com.nova.macos.genie", "14.0", "NOVA/Info.plist"
    )
    rel_paths = [
        p
        for p in _parse_pbx_source_paths(pbx)
        if p.endswith(".swift")
        and ("/" in p or p.endswith(".swift"))
        and "Tests" not in p
        and not p.startswith("NOVAGenie")
    ]
    assert rel_paths, "expected app Swift paths in pbxproj"
    for rel in rel_paths:
        assert " " not in rel or rel.startswith('"') is False
        full = app_dir / rel
        assert full.is_file(), f"missing source file for path={rel!r}"
        assert not full.is_dir(), f"path points to directory: {rel!r}"
        assert is_valid_swift_source(full)
    assert not any(p.strip() in (".swift", "") for p in rel_paths)
    assert not any(p.endswith("/.swift") for p in rel_paths)


def test_ios_generated_paths_resolve_to_files() -> None:
    app_dir = ROOT / "apps" / "ios" / "NOVA"
    pbx = generate_pbxproj("NOVA", app_dir, "ios", "com.nova.ios", "17.0", "NOVA/Info.plist")
    rel_paths = [
        p
        for p in _parse_pbx_source_paths(pbx)
        if p.endswith(".swift") and "/" in p and "Tests" not in p
    ]
    for rel in rel_paths:
        full = app_dir / rel
        assert full.is_file(), rel


def test_regenerate_macos_pbxproj_is_deterministic() -> None:
    app_dir = ROOT / "apps" / "macos" / "NOVA"
    a = generate_macos_pbxproj(
        "NOVAGenie", app_dir, "com.nova.macos.genie", "14.0", "NOVA/Info.plist"
    )
    b = generate_macos_pbxproj(
        "NOVAGenie", app_dir, "com.nova.macos.genie", "14.0", "NOVA/Info.plist"
    )
    assert a == b

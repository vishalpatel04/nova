"""Performance exclusions — skippable for speed, not permanent privacy blocks."""

from __future__ import annotations

from pathlib import Path

DEFAULT_PERFORMANCE_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "build",
        "dist",
        "DerivedData",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        ".npm",
        ".cache",
        "Caches",
        "Cache",
    }
)

BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".dmg",
        ".pkg",
        ".iso",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".rar",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".mp3",
        ".wav",
        ".flac",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".heic",
        ".sqlite",
        ".db",
        ".wasm",
    }
)

MAX_INDEX_FILE_BYTES = 5 * 1024 * 1024


def should_skip_dir(name: str, *, override_performance: bool = False) -> bool:
    if override_performance:
        return name in {".git"}  # still skip git objects dir name at top level only
    if name in DEFAULT_PERFORMANCE_DIR_NAMES:
        return True
    return name.startswith(".") and name not in {".", ".."}


def should_skip_file(path: Path, *, override_performance: bool = False) -> bool:
    if path.name.startswith(".") and path.name not in {".", ".."}:
        return True
    if not override_performance and path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        if path.stat().st_size > MAX_INDEX_FILE_BYTES:
            return True
    except OSError:
        return True
    return False


def is_text_extractable(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in {
        ".txt",
        ".md",
        ".rst",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".csv",
        ".swift",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".sql",
        ".html",
        ".css",
        ".sh",
        ".toml",
        ".ini",
        ".cfg",
        ".xml",
    }:
        return True
    if ext in {".pdf", ".docx", ".pptx", ".xlsx"}:
        return False  # metadata only until adapters added
    return ext == "" or len(ext) <= 5

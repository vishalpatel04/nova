"""Safe local text extraction for indexing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nova_core.memory.exclusions import MAX_INDEX_FILE_BYTES
from nova_core.memory.vault import assert_not_vault_path


@dataclass(frozen=True)
class ExtractedContent:
    text: str
    truncated: bool
    mime_type: str


def extract_text(path: Path) -> ExtractedContent | None:
    assert_not_vault_path(str(path))
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_INDEX_FILE_BYTES:
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:512]:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    truncated = len(text) > 12000
    return ExtractedContent(
        text=text[:12000],
        truncated=truncated,
        mime_type="text/plain",
    )


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 80) -> list[str]:
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]

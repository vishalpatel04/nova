"""Alembic revision identifiers must fit alembic_version.version_num (VARCHAR 32)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MAX_REVISION_LENGTH = 32


def test_all_alembic_revision_ids_fit_version_num_column() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    revisions = list(script.walk_revisions())
    assert revisions, "expected at least one Alembic revision"

    for rev in revisions:
        assert len(rev.revision) <= MAX_REVISION_LENGTH, (
            f"revision {rev.revision!r} is {len(rev.revision)} chars "
            f"(max {MAX_REVISION_LENGTH}) in {rev.path}"
        )
        if rev.down_revision is None:
            continue
        down_ids = (
            rev.down_revision if isinstance(rev.down_revision, tuple) else (rev.down_revision,)
        )
        for down_id in down_ids:
            assert len(down_id) <= MAX_REVISION_LENGTH, (
                f"down_revision {down_id!r} is {len(down_id)} chars "
                f"(max {MAX_REVISION_LENGTH}) for {rev.revision!r}"
            )

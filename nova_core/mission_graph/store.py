"""MissionGraph evidence persistence."""

from __future__ import annotations

import json
from pathlib import Path

from nova_core.agent_os.workspace import runs_dir
from nova_core.mission_graph.models import MissionGraphEvidence


class MissionGraphStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (runs_dir() / "mission-graphs")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, mission_id: str) -> Path:
        return self.base_dir / f"{mission_id}.graph.json"

    def save(self, evidence: MissionGraphEvidence) -> str:
        path = self._path(evidence.mission_id)
        path.write_text(json.dumps(evidence.to_dict(), indent=2), encoding="utf-8")
        return str(path)

    def load(self, mission_id: str) -> MissionGraphEvidence | None:
        path = self._path(mission_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return MissionGraphEvidence(
            graph_version=str(data.get("graph_version", "")),
            mission_id=str(data.get("mission_id", mission_id)),
            nodes=list(data.get("nodes") or []),
            edges=list(data.get("edges") or []),
            state_snapshots=list(data.get("state_snapshots") or []),
            engine_selected=str(data.get("engine_selected", "")),
            approvals=list(data.get("approvals") or []),
            final_report=dict(data.get("final_report") or {}),
        )

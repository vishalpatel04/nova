"""Agent mission persistence and execution."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from nova_core.agent_os.models import AgentMission, MissionStatus, utc_now_iso
from nova_core.agent_os.prime import classify_request, is_calculator_mission
from nova_core.agent_os.sentry import review_action
from nova_core.agent_os.timeline import (
    append_timeline,
    format_final_report_cli,
    format_timeline_cli,
)
from nova_core.agent_os.workspace import redact_secrets, runs_dir
from nova_core.orchestration.app_builder import build_calculator_app, clean_calculator_workspace


class MissionStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or runs_dir()

    def _path(self, mission_id: str) -> Path:
        return self.base_dir / f"{mission_id}.json"

    def save(self, mission: AgentMission) -> None:
        path = self._path(mission.mission_id)
        path.write_text(json.dumps(mission.to_dict(), indent=2), encoding="utf-8")
        mission.evidence_log_path = str(path)

    def load(self, mission_id: str) -> AgentMission | None:
        path = self._path(mission_id)
        if not path.exists():
            return None
        return AgentMission.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.base_dir.glob("*.json"))


class AgentMissionRunner:
    def __init__(self, store: MissionStore | None = None) -> None:
        self.store = store or MissionStore()

    def create_mission(self, user_request: str) -> AgentMission:
        classification = classify_request(user_request)
        mission_id = str(uuid.uuid4())
        now = utc_now_iso()
        mission = AgentMission(
            mission_id=mission_id,
            user_request=user_request,
            mission_type=classification.mission_type,
            commander=classification.commander,
            squad=list(classification.squad),
            status=MissionStatus.PENDING,
            risk_level=classification.risk_level,
            acceptance_criteria=list(classification.acceptance_criteria),
            timeline_events=[],
            skill_calls=[],
            files_touched=[],
            commands_run=[],
            validation_results=[],
            approvals_required=["deploy.vercel_deploy"] if "deploy" in user_request.lower() else [],
            artifacts={},
            final_report={},
            created_at=now,
            updated_at=now,
        )
        self.store.save(mission)
        return mission

    def run_mission(
        self,
        user_request: str,
        *,
        run_npm: bool = True,
        clean_workspace: bool = False,
    ) -> AgentMission:
        mission = self.create_mission(user_request)
        mission.status = MissionStatus.RUNNING
        append_timeline(
            mission,
            agent_id="prime",
            display_name="Prime",
            message=f"Classified mission: {mission.mission_type}",
        )
        append_timeline(
            mission,
            agent_id="archive",
            display_name="Archive",
            message="Retrieved context: full-local mode active, workspace policy loaded",
        )

        if is_calculator_mission(user_request):
            return self._run_calculator_mission(
                mission, run_npm=run_npm, clean_workspace=clean_workspace
            )

        append_timeline(
            mission,
            agent_id="prime",
            display_name="Prime",
            message="Mission type not yet automated — routed to Archive context only",
        )
        mission.status = MissionStatus.COMPLETED
        mission.final_report = {
            "summary": "Mission recorded; no automated executor for this type yet.",
        }
        self.store.save(mission)
        return mission

    def _run_calculator_mission(
        self,
        mission: AgentMission,
        *,
        run_npm: bool,
        clean_workspace: bool,
    ) -> AgentMission:
        append_timeline(
            mission,
            agent_id="forge",
            display_name="Forge",
            message=(
                "Squad activated: Product Planner, Architect, Frontend Engineer, "
                "QA Engineer, Code Reviewer, Deploy Engineer, Sentry"
            ),
        )
        append_timeline(
            mission,
            agent_id="product_planner",
            display_name="Product Planner",
            message="Acceptance criteria ready",
        )
        append_timeline(
            mission,
            agent_id="architect",
            display_name="Architect",
            message="Stack selected: Vite + React + TypeScript",
        )

        if clean_workspace:
            clean_calculator_workspace()

        build = build_calculator_app(run_npm=run_npm)
        mission.workspace_path = build.project_path
        mission.files_touched = build.files_written

        append_timeline(
            mission,
            agent_id="frontend_engineer",
            display_name="Frontend Engineer",
            message="Generated calculator app files",
            evidence={"file_count": len(build.files_written)},
        )

        if build.install:
            mission.commands_run.append(
                {
                    "command": build.install.command,
                    "exit_code": build.install.exit_code,
                    "success": build.install.success,
                }
            )
            append_timeline(
                mission,
                agent_id="qa_engineer",
                display_name="QA Engineer",
                message=f"npm install: {'PASS' if build.install.success else 'FAIL'}",
            )

        if build.build:
            mission.commands_run.append(
                {
                    "command": build.build.command,
                    "exit_code": build.build.exit_code,
                    "success": build.build.success,
                }
            )
            mission.validation_results.append(
                {
                    "step": "npm run build",
                    "passed": build.build.success,
                }
            )
            append_timeline(
                mission,
                agent_id="qa_engineer",
                display_name="QA Engineer",
                message=f"npm run build: {'PASS' if build.build.success else 'FAIL'}",
            )

        append_timeline(
            mission,
            agent_id="fixer",
            display_name="Fixer",
            message="No fixes needed" if build.build_passed else "Fixes required — build failed",
        )
        append_timeline(
            mission,
            agent_id="code_reviewer",
            display_name="Code Reviewer",
            message=f"Static review: {'PASS' if build.build_passed else 'BLOCKED'}",
        )

        if build.build_passed and build.preview_url:
            mission.preview_url = build.preview_url
            append_timeline(
                mission,
                agent_id="devops_deploy",
                display_name="Deploy Engineer",
                message=f"Local preview: {build.preview_url}",
            )

        deploy_review = review_action("deploy.vercel_deploy")
        append_timeline(
            mission,
            agent_id="sentry",
            display_name="Sentry",
            message="External deployment requires approval",
            evidence={"requires_approval": deploy_review.requires_approval},
        )

        mission.status = (
            MissionStatus.WAITING_APPROVAL
            if deploy_review.requires_approval
            else MissionStatus.COMPLETED
        )
        mission.final_report = {
            "path": build.project_path,
            "build_status": "PASS" if build.build_passed else "FAIL",
            "preview_url": build.preview_url,
            "deployment_status": "approval required",
            "evidence_log": str(self.store._path(mission.mission_id)),
        }
        append_timeline(
            mission,
            agent_id="prime",
            display_name="Prime",
            message="Mission complete with evidence",
        )
        self.store.save(mission)
        return mission

    def approve_deployment(self, mission_id: str) -> AgentMission:
        mission = self.store.load(mission_id)
        if mission is None:
            raise ValueError(f"Mission not found: {mission_id}")
        verdict = review_action("deploy.vercel_deploy", context={"approved": True})
        if not verdict.requires_approval:
            mission.final_report["deployment_status"] = "approved — deploy still manual in v1"
            mission.status = MissionStatus.COMPLETED
        append_timeline(
            mission,
            agent_id="sentry",
            display_name="Sentry",
            message="Deployment approval recorded",
        )
        self.store.save(mission)
        return mission

    def deploy_mission(self, mission_id: str) -> AgentMission:
        mission = self.approve_deployment(mission_id)
        append_timeline(
            mission,
            agent_id="devops_deploy",
            display_name="Deploy Engineer",
            message="External deploy prepared — manual Vercel step not executed in demo v1",
        )
        mission.final_report["deployment_status"] = "prepared — external deploy not auto-run in v1"
        self.store.save(mission)
        return mission

    def format_cli_output(self, mission: AgentMission) -> str:
        body = format_timeline_cli(mission) + format_final_report_cli(mission)
        return redact_secrets(body)


def archive_search_response(query: str, hits: list[dict[str, Any]], *, access_profile: str) -> str:
    if not hits:
        return (
            f'Archive search for "{query}" found no local matches.\n'
            f"Access profile: {access_profile} (full-local read/search enabled)."
        )
    lines = [
        f'Archive local search for "{query}" ({access_profile}):',
        f"Found {len(hits)} matches:",
    ]
    for hit in hits[:8]:
        lines.append(f"- [{hit.get('kind', 'item')}] {hit.get('summary', '')}")
    return redact_secrets("\n".join(lines))

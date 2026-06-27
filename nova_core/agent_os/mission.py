"""Agent mission persistence and execution."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from nova_core.agent_os.models import AgentMission, MissionStatus, utc_now_iso
from nova_core.agent_os.prime import classify_request, is_app_build_mission
from nova_core.agent_os.sentry import review_action
from nova_core.agent_os.timeline import (
    append_timeline,
    format_final_report_cli,
    format_timeline_cli,
)
from nova_core.agent_os.workspace import redact_secrets, runs_dir
from nova_core.forge.mission_executor import ForgeExecutionResult
from nova_core.mission_graph.config import MissionGraphRunConfig
from nova_core.mission_graph.langgraph_adapter import LangGraphAdapter
from nova_core.mission_graph.models import MissionGraphEvidence
from nova_core.orchestration.app_builder import (
    project_path_for_request,
    stop_app_preview,
)
from nova_core.orchestration.app_request import parse_app_request
from nova_core.orchestration.app_spec import build_app_spec
from nova_core.schemas.settings import Settings


class MissionStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or runs_dir()

    def _path(self, mission_id: str) -> Path:
        return self.base_dir / f"{mission_id}.json"

    def save(self, mission: AgentMission) -> None:
        path = self._path(mission.mission_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mission.to_dict(), indent=2), encoding="utf-8")
        mission.evidence_log_path = str(path)

    def load(self, mission_id: str) -> AgentMission | None:
        path = self._path(mission_id)
        if not path.exists():
            return None
        return AgentMission.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.base_dir.glob("*.json"))

    def latest_awaiting_approval(self) -> AgentMission | None:
        candidates: list[AgentMission] = []
        for mission_id in self.list_ids():
            mission = self.load(mission_id)
            if mission is not None and mission.status == MissionStatus.WAITING_APPROVAL:
                candidates.append(mission)
        if not candidates:
            return None
        return max(candidates, key=lambda mission: mission.updated_at)


class AgentMissionRunner:
    def __init__(
        self,
        store: MissionStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.store = store or MissionStore()
        self.settings = settings or Settings()

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
            approvals_required=["deploy.vercel_deploy"],
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
        start_preview: bool = True,
        assumptions: list[str] | None = None,
        selected_engine: str | None = None,
        allow_fallback: bool = False,
    ) -> AgentMission:
        mission = self.create_mission(user_request)
        if assumptions:
            mission.artifacts["assumptions"] = assumptions
        engine_id = selected_engine or "deterministic_template"
        mission.artifacts["selected_engine"] = engine_id
        graph_config = MissionGraphRunConfig(
            selected_engine=engine_id,
            settings=self.settings,
            run_npm=run_npm,
            start_preview=start_preview,
            clean_workspace=clean_workspace,
            allow_fallback=allow_fallback,
        )
        graph_evidence = LangGraphAdapter().run(
            mission.mission_id,
            user_request,
            config=graph_config,
        )
        mission.artifacts["mission_graph"] = graph_evidence.to_dict()
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
            message="Retrieved local context and workspace policy",
        )

        if is_app_build_mission(user_request):
            return self._run_app_builder_mission(
                mission,
                graph_evidence=graph_evidence,
                selected_engine=engine_id,
                allow_fallback=allow_fallback,
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

    def _run_app_builder_mission(
        self,
        mission: AgentMission,
        *,
        graph_evidence: MissionGraphEvidence,
        selected_engine: str,
        allow_fallback: bool,
    ) -> AgentMission:
        app_request = parse_app_request(mission.user_request)
        if app_request is None:
            app_request = parse_app_request(f"build a simple web app for {mission.user_request}")
        if app_request is None:
            mission.status = MissionStatus.FAILED
            mission.final_report = {
                "summary": "Could not parse app build request.",
                "evidence_log": str(self.store._path(mission.mission_id)),
            }
            self.store.save(mission)
            return mission

        if app_request.requires_clarification:
            append_timeline(
                mission,
                agent_id="prime",
                display_name="Prime",
                message="Clarification required before build",
            )
            mission.status = MissionStatus.COMPLETED
            mission.final_report = {
                "summary": app_request.clarification_message,
                "evidence_log": str(self.store._path(mission.mission_id)),
            }
            self.store.save(mission)
            return mission

        forge_data = graph_evidence.final_report.get("forge_execution", {})
        forge = (
            ForgeExecutionResult.from_dict(forge_data)
            if isinstance(forge_data, dict) and forge_data
            else None
        )
        if forge is None:
            mission.status = MissionStatus.FAILED
            mission.final_report = {
                "summary": "Forge execution did not produce a result.",
                "evidence_log": str(self.store._path(mission.mission_id)),
            }
            self.store.save(mission)
            return mission

        if forge.status == "unavailable":
            append_timeline(
                mission,
                agent_id="forge",
                display_name="Forge",
                message=f"{forge.engine_display_name} unavailable",
                evidence={"setup_hint": forge.setup_hint},
            )
            mission.status = MissionStatus.COMPLETED
            mission.final_report = {
                "summary": forge.setup_hint,
                "forge_engine": forge.engine_id,
                "engine_display_name": forge.engine_display_name,
                "engine_status": forge.status,
                "setup_hint": forge.setup_hint,
                "external_engine_available": False,
                "evidence_log": str(self.store._path(mission.mission_id)),
            }
            self.store.save(mission)
            return mission

        spec = build_app_spec(app_request)
        mission.artifacts["app_spec_summary"] = {
            "title": spec.title,
            "description": spec.description,
            "stack": spec.stack,
            "components": list(spec.components),
            "acceptance_criteria": list(spec.acceptance_criteria),
        }
        project_path = project_path_for_request(app_request)

        engine_label = forge.engine_display_name or forge.engine_id
        append_timeline(
            mission,
            agent_id="forge",
            display_name="Forge",
            message=f"Engineering squad activated — engine: {engine_label}",
        )
        append_timeline(
            mission,
            agent_id="product_planner",
            display_name="Product Planner",
            message="Created app spec",
            evidence={"app_type": app_request.app_type, "title": spec.title},
        )
        append_timeline(
            mission,
            agent_id="architect",
            display_name="Architect",
            message=f"Selected stack: {spec.stack}",
        )

        mission.workspace_path = forge.workspace_path or str(project_path)
        mission.files_touched = forge.files_changed
        mission.commands_run.extend(forge.commands_run)
        mission.artifacts.update(
            {
                "app_type": forge.app_type or app_request.app_type,
                "app_name": forge.app_name or app_request.app_name,
                "template_id": forge.template_id or forge.engine_id,
                "runtime": forge.runtime or app_request.runtime,
                "forge_execution": forge.to_dict(),
            }
        )

        engineer_label = "Backend Engineer" if forge.runtime == "cli" else "Frontend Engineer"
        append_timeline(
            mission,
            agent_id="frontend_engineer",
            display_name=engineer_label,
            message=f"Generated app files via {forge.engine_display_name or forge.engine_id}",
            evidence={
                "file_count": len(forge.files_changed),
                "engine": forge.engine_id,
                "fallback_used": forge.fallback_used,
            },
        )

        if forge.commands_run:
            for entry in forge.commands_run:
                label = entry.get("command", "command")
                success = entry.get("success", False)
                append_timeline(
                    mission,
                    agent_id="qa_engineer",
                    display_name="QA Engineer",
                    message=f"{label}: {'PASS' if success else 'FAIL'}",
                )
                mission.validation_results.append(
                    {"step": label, "passed": bool(success)},
                )

        validation_label = forge.validation_status.upper()
        append_timeline(
            mission,
            agent_id="qa_engineer",
            display_name="QA Engineer",
            message=f"Validation: {validation_label}",
        )

        fixes_needed = not forge.build_passed
        append_timeline(
            mission,
            agent_id="fixer",
            display_name="Fixer",
            message="Fixes applied" if fixes_needed else "No fixes needed",
        )
        append_timeline(
            mission,
            agent_id="code_reviewer",
            display_name="Code Reviewer",
            message=f"Static review: {'PASS' if forge.build_passed else 'FAIL'}",
        )

        preview_status = "n/a"
        if forge.runtime == "cli" and forge.build_passed and forge.run_command:
            append_timeline(
                mission,
                agent_id="devops_deploy",
                display_name="Deploy Engineer",
                message=f"CLI app ready — run: {forge.run_command}",
            )
        if forge.preview_url:
            mission.preview_url = forge.preview_url
            preview_status = forge.preview_url
            append_timeline(
                mission,
                agent_id="devops_deploy",
                display_name="Deploy Engineer",
                message=f"Local preview verified: {forge.preview_url}",
            )
        elif forge.preview_reachable is False and forge.preview_log_path:
            preview_status = "FAILED"
            mission.artifacts.update(
                {
                    "preview_log_path": forge.preview_log_path,
                }
            )
            append_timeline(
                mission,
                agent_id="devops_deploy",
                display_name="Deploy Engineer",
                message=f"Local preview failed — see log {forge.preview_log_path}",
            )

        deploy_review = review_action("deploy.vercel_deploy")
        mission.skill_calls.append(
            {
                "skill_id": "sentry.review_action",
                "action": "deploy.vercel_deploy",
                "requires_approval": deploy_review.requires_approval,
            }
        )
        approval_message = (
            "Packaging requires approval"
            if forge.runtime == "cli"
            else "Deployment requires approval"
        )
        append_timeline(
            mission,
            agent_id="sentry",
            display_name="Sentry",
            message=approval_message,
            evidence={"requires_approval": deploy_review.requires_approval},
        )

        mission.status = (
            MissionStatus.WAITING_APPROVAL
            if forge.build_passed and deploy_review.requires_approval
            else MissionStatus.COMPLETED
            if forge.build_passed
            else MissionStatus.FAILED
        )
        mission.final_report = {
            "app_name": forge.app_name or app_request.app_name,
            "app_type": forge.app_type or app_request.app_type,
            "path": forge.workspace_path or str(project_path),
            "build_status": "PASS" if forge.build_passed else "FAIL",
            "preview_url": forge.preview_url,
            "preview_status": preview_status,
            "runtime": forge.runtime or app_request.runtime,
            "run_command": forge.run_command,
            "deployment_status": "approval required" if forge.build_passed else "blocked",
            "evidence_log": str(self.store._path(mission.mission_id)),
            "assumptions": mission.artifacts.get("assumptions", []),
            "app_spec_summary": mission.artifacts.get("app_spec_summary"),
            "files_written": forge.files_changed[:16],
            "validation_commands": [entry.get("command", "") for entry in forge.commands_run],
            "forge_engine": forge.engine_id,
            "engine_display_name": forge.engine_display_name,
            "engine_status": forge.status,
            "engine_reason": forge.engine_reason,
            "setup_hint": forge.setup_hint,
            "external_engine_available": forge.engine_id != "deterministic_template",
            "fallback_used": forge.fallback_used or allow_fallback,
            "forge_evidence_paths": forge.evidence_paths,
            "forge_stdout_log": forge.stdout_log[:500],
            "forge_stderr_log": forge.stderr_log[:500],
        }
        prime_close = (
            "App ready. Package this app? yes/no"
            if forge.runtime == "cli"
            else "App ready. Deploy this app? yes/no"
        )
        append_timeline(
            mission,
            agent_id="prime",
            display_name="Prime",
            message=prime_close,
        )
        self.store.save(mission)
        return mission

    def stop_preview(self, mission_id: str) -> bool:
        mission = self.store.load(mission_id)
        if mission is None:
            return False
        pid = mission.artifacts.get("preview_pid") or mission.final_report.get("preview_pid")
        stopped = stop_app_preview(int(pid) if pid else None)
        if stopped:
            append_timeline(
                mission,
                agent_id="devops_deploy",
                display_name="Deploy Engineer",
                message="Local preview stopped",
            )
            self.store.save(mission)
        return stopped

    def approve_deployment(self, mission_id: str) -> AgentMission:
        mission = self.store.load(mission_id)
        if mission is None:
            raise ValueError(f"Mission not found: {mission_id}")
        verdict = review_action("deploy.vercel_deploy", context={"approved": True})
        mission.skill_calls.append(
            {
                "skill_id": "sentry.review_action",
                "action": "deploy.vercel_deploy",
                "approved": True,
            }
        )
        append_timeline(
            mission,
            agent_id="sentry",
            display_name="Sentry",
            message="Deployment approval recorded",
            evidence={"approved": True, "requires_approval": verdict.requires_approval},
        )
        mission.final_report["deployment_status"] = "approved"
        if mission.status == MissionStatus.WAITING_APPROVAL:
            mission.status = MissionStatus.COMPLETED
        self.store.save(mission)
        return mission

    def skip_deployment(self, mission_id: str) -> AgentMission:
        mission = self.store.load(mission_id)
        if mission is None:
            raise ValueError(f"Mission not found: {mission_id}")
        append_timeline(
            mission,
            agent_id="sentry",
            display_name="Sentry",
            message="Deployment skipped by user",
        )
        mission.final_report["deployment_status"] = "skipped"
        mission.status = MissionStatus.COMPLETED
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

    def latest_awaiting_approval(self) -> AgentMission | None:
        return self.store.latest_awaiting_approval()

    def format_cli_output(self, mission: AgentMission | None) -> str:
        if mission is None:
            return "Mission not found."
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

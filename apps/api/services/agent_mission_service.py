"""Agent OS API service — missions, archive search, memory status."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.memory_kernel import MemoryKernelService
from nova_core.agent_os.mission import AgentMissionRunner, MissionStore, archive_search_response
from nova_core.agent_os.models import AgentMission
from nova_core.agent_os.registry import list_agents, list_forge_specialists
from nova_core.agent_os.skills import list_skills
from nova_core.agent_os.workspace import workspace_root
from nova_core.memory.access_policy import AccessProfile
from nova_core.memory.retrieval import format_retrieval_result
from nova_core.orchestration.app_request import is_app_build_intent, parse_app_request
from nova_core.schemas.settings import Settings
from nova_core.tools.personal_search import PersonalSearchTool


class AgentMissionService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.runner = AgentMissionRunner(settings=settings)
        self.memory = MemoryKernelService(session, settings)

    async def ensure_full_local(self, user_id: str) -> None:
        cfg = await self.memory.get_or_create_settings(user_id)
        if cfg.access_profile != AccessProfile.FULL_LOCAL.value:
            await self.memory.set_access_profile(user_id, AccessProfile.FULL_LOCAL)

    async def memory_status_text(self, user_id: str) -> str:
        overview = await self.memory.status_overview(user_id)
        last_scan = "never"
        for source in overview.get("sources", []):
            if source.get("last_scan_at"):
                last_scan = source["last_scan_at"]
        indexing_state = "paused" if overview.get("indexing_paused") else "active"
        return (
            "NOVA memory status (local-only):\n"
            f"- Access profile: {overview['access_profile']}\n"
            f"- Local only: {overview['local_only']}\n"
            f"- Active sources: {len(overview.get('sources', []))}\n"
            f"- Documents discovered: {overview['documents_discovered']}\n"
            f"- Documents indexed: {overview['documents_indexed']}\n"
            f"- Chunks: {overview['chunks']}\n"
            f"- Entities: {overview['entities']}\n"
            f"- Relationships: {overview['relationships']}\n"
            f"- Pending jobs: {overview['pending_jobs']}\n"
            f"- Embedding health: {overview['embedding_health']}\n"
            f"- Last scan: {last_scan}\n"
            f"- Indexing state: {indexing_state}"
        )

    async def archive_search(self, user_id: str, query: str) -> str:
        await self.ensure_full_local(user_id)
        cfg = await self.memory.get_or_create_settings(user_id)
        profile = cfg.access_profile

        retrieval = await self.memory.retrieve(user_id, query, limit=10)
        hits: list[dict[str, Any]] = [
            {
                "kind": h.kind,
                "summary": h.summary,
                "score": h.score,
                "provenance": h.provenance,
            }
            for h in retrieval.hits
        ]

        policy = await self.memory.get_access_policy(user_id)
        roots = [str(r) for r in policy.allowed_roots()]
        file_tool = PersonalSearchTool(search_roots=roots)
        file_result = file_tool.search_all_approved(query)
        if file_result.success and file_result.output:
            output = file_result.output
            for path in list((output.get("by_file") or {}).keys())[:8]:
                hits.append(
                    {
                        "kind": "file",
                        "summary": path,
                        "score": 0.5,
                        "provenance": "local_filesystem",
                    }
                )

        if hits:
            return archive_search_response(query, hits, access_profile=profile)
        return format_retrieval_result(retrieval)

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
        return self.runner.run_mission(
            user_request,
            run_npm=run_npm,
            clean_workspace=clean_workspace,
            start_preview=start_preview,
            assumptions=assumptions,
            selected_engine=selected_engine,
            allow_fallback=allow_fallback,
        )

    def get_mission(self, mission_id: str) -> AgentMission | None:
        return self.runner.store.load(mission_id)

    def latest_awaiting_approval(self) -> AgentMission | None:
        return self.runner.latest_awaiting_approval()

    def mission_timeline_text(self, mission_id: str) -> str:
        mission = self.get_mission(mission_id)
        if mission is None:
            return f"Mission not found: {mission_id}"
        return self.runner.format_cli_output(mission)

    def approve_deployment(self, mission_id: str) -> AgentMission:
        return self.runner.approve_deployment(mission_id)

    def skip_deployment(self, mission_id: str) -> AgentMission:
        return self.runner.skip_deployment(mission_id)

    def deploy_mission(self, mission_id: str) -> AgentMission:
        return self.runner.deploy_mission(mission_id)

    def stop_preview(self, mission_id: str) -> bool:
        return self.runner.stop_preview(mission_id)

    @staticmethod
    def list_agent_catalog() -> dict[str, Any]:
        return {
            "leadership": [a.__dict__ for a in list_agents()],
            "forge_specialists": [a.__dict__ for a in list_forge_specialists()],
        }

    @staticmethod
    def list_skill_catalog() -> list[dict[str, Any]]:
        return [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "department": s.department,
                "required_permission_level": int(s.required_permission_level),
                "requires_approval": s.requires_approval,
            }
            for s in list_skills()
        ]

    @staticmethod
    def status_summary() -> dict[str, Any]:
        return {
            "agent_os": "v1",
            "workspace_root": str(workspace_root()),
            "missions_dir": str(MissionStore().base_dir),
        }


def parse_archive_search_query(text: str) -> str | None:
    patterns = (
        r"^search my mac for (.+)$",
        r"^search my computer for (.+)$",
        r"^can you find (.+?) in my pc$",
        r"^find (.+?) on my mac$",
        r"^find (.+?) in my pc$",
        r"^do i have anything about (.+)$",
        r"^what do you know about (.+?) from my files$",
        r"^search my memory for (.+)$",
        r"^find latest (.+)$",
    )
    normalized = re.sub(r"\s+", " ", text.strip())
    for pattern in patterns:
        match = re.match(pattern, normalized, re.I)
        if match:
            return match.group(1).strip().rstrip("?")
    return None


def is_agent_os_mission_request(text: str) -> bool:
    if is_app_build_intent(text):
        return True
    from nova_core.forge.selector import _EXPLICIT_ENGINE_PATTERNS

    return any(pattern.search(text) for pattern, _ in _EXPLICIT_ENGINE_PATTERNS)


def normalize_build_app_request(short_name: str) -> str:
    """Turn CLI `build-app` shorthand into a natural mission request."""
    cleaned = short_name.strip()
    lowered = cleaned.lower()
    if parse_app_request(f"build {cleaned}") is not None:
        return f"build {cleaned}"
    if "landing" in lowered:
        return f"build a landing page for {cleaned.replace('landing page for', '').strip()}"
    return f"build a {cleaned}"


def is_memory_status_request(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered in {"memory status", "show memory status"}


def is_system_memory_status_request(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered in {
        "system memory status",
        "ram usage",
        "ram status",
        "memory usage",
    }


_DEPLOY_YES = frozenset(
    {
        "yes",
        "y",
        "approve",
        "deploy it",
        "deploy",
        "package it",
        "approve deployment",
        "approve deploy",
    }
)
_DEPLOY_NO = frozenset({"no", "n", "skip", "skip deploy", "not now", "don't deploy", "dont deploy"})


def resolve_deployment_chat_intent(text: str) -> tuple[str, dict[str, str]] | None:
    lowered = text.lower().strip()
    awaiting = AgentMissionRunner().latest_awaiting_approval()

    if lowered in _DEPLOY_YES:
        if awaiting is not None:
            return "agent_os_deploy_yes", {}
        if lowered in {"approve deployment", "approve deploy", "deploy it"}:
            return "agent_os_approve_deploy", {}
        return None

    if lowered in _DEPLOY_NO and awaiting is not None:
        return "agent_os_deploy_no", {}

    if lowered == "deploy it" and awaiting is not None:
        return "agent_os_deploy_yes", {}

    return None


def is_preview_request(text: str) -> bool:
    return text.lower().strip() in {"preview it", "show preview", "open preview"}

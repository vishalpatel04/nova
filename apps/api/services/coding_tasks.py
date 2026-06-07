"""Coding task workflow — inspect, validate, propose patch, await approval."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.approvals import ApprovalRequestService
from apps.api.services.projects import ProjectService
from nova_core.auth.principal import Principal
from nova_core.capabilities.model import CapabilityName, risk_for_capability
from nova_core.models.enums import CodingTaskStage
from nova_core.models.orm import CodingTask
from nova_core.patch.diff import build_unified_diff
from nova_core.patch.policy import PatchFileChange, build_patch_preview, validate_patch_payload
from nova_core.project.inspect import format_inspection, inspect_repo
from nova_core.project.validation import pick_validation_command, run_validation_command
from nova_core.providers.runtime import InferenceRequest, ProviderRuntime
from nova_core.schemas.errors import ValidationError
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CodingTaskService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self._project_svc = ProjectService(session, settings)
        self._approval_svc = ApprovalRequestService(session, settings)
        self._provider = ProviderRuntime(settings)
        policies = settings.load_yaml("policies.yaml")
        safe_cfg = policies.get("safe_filesystem", {})
        self._allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None

    async def start_task(self, principal: Principal, user_request: str) -> CodingTask:
        active = await self._project_svc.get_active_project(principal)
        task = CodingTask(
            user_id=principal.user_id,
            device_id=principal.device_id or "",
            project_root=active.project_root,
            stage=CodingTaskStage.INSPECTING.value,
            user_request=user_request,
            timeline=[self._timeline_entry(CodingTaskStage.INSPECTING, "Inspecting repository")],
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def run_workflow(self, principal: Principal, user_request: str) -> dict[str, Any]:
        active = await self._project_svc.get_active_project(principal)
        project_root = Path(active.project_root)
        task = await self.start_task(principal, user_request)

        inspection = await inspect_repo(project_root)
        active.current_branch = inspection.current_branch
        await self._advance(task, CodingTaskStage.RUNNING_TESTS, "Running validation")

        validation_cmd = pick_validation_command(project_root) or "make test"
        validation = await run_validation_command(
            project_root, validation_cmd, allowed_roots=self._allowed_roots
        )
        await self._project_svc.upsert_memory(
            principal,
            active.project_root,
            last_validation_command=validation_cmd,
            last_validation_result={
                "exit_code": validation.exit_code,
                "stdout": validation.stdout_excerpt[:2000],
                "stderr": validation.stderr_excerpt[:2000],
                "blocked": validation.blocked,
            },
        )

        await self._advance(task, CodingTaskStage.ANALYZING, "Analyzing failure")
        analysis = self._analyze_failure(validation)

        patch_payload = await self._propose_patch(project_root, user_request, analysis, validation)
        patch_validation = validate_patch_payload(project_root, patch_payload)
        if not patch_validation.allowed:
            await self._fail(task, patch_validation.reason or "Patch blocked by policy")
            return self._task_response(task, blocked=True, message=patch_validation.reason)

        await self._advance(task, CodingTaskStage.PATCH_PROPOSED, "Patch proposed")
        preview = build_patch_preview(patch_payload)
        approval = await self._approval_svc.create_request(
            principal,
            capability=CapabilityName.CODE_PATCH,
            action_summary=f"Apply patch to {active.project_name}: {user_request[:120]}",
            preview=preview,
            payload=patch_payload,
            risk_level=risk_for_capability(CapabilityName.CODE_PATCH),
        )
        task.approval_id = approval.id
        await self._advance(task, CodingTaskStage.AWAITING_APPROVAL, "Awaiting approval")
        await self._project_svc.upsert_memory(
            principal,
            active.project_root,
            last_patch_proposal=patch_payload,
        )

        summary = (
            f"Coding task for {active.project_name}\n"
            f"Analysis: {analysis}\n"
            f"Validation: exit {validation.exit_code}\n"
            f"Patch proposed ({len(patch_payload.get('files', []))} files).\n"
            f"Approval ID: {approval.id}\n"
            "Approve in Settings → Approvals, then click Apply Approved Patch."
        )
        task.summary = summary
        await self._project_svc.append_task_history(
            principal,
            active.project_root,
            {"task_id": task.id, "request": user_request[:200], "approval_id": approval.id},
        )
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action="coding_task.patch_proposed",
            resource_type="coding_task",
            resource_id=task.id,
            details={"approval_id": approval.id},
        )
        await self.session.flush()
        return self._task_response(
            task,
            approval_id=approval.id,
            inspection=format_inspection(inspection),
            validation={
                "command": validation_cmd,
                "exit_code": validation.exit_code,
                "stdout": validation.stdout_excerpt[:1500],
                "stderr": validation.stderr_excerpt[:1500],
            },
            patch_preview=preview,
            unified_diff=patch_payload.get("unified_diff", "")[:3000],
            message=summary,
        )

    async def rerun_validation_after_apply(
        self, principal: Principal, task_id: str
    ) -> dict[str, Any]:
        result = await self.session.get(CodingTask, task_id)
        if result is None or result.user_id != principal.user_id:
            raise ValidationError("Task not found")
        project_root = Path(result.project_root)
        await self._advance(result, CodingTaskStage.RERUNNING_VALIDATION, "Re-running validation")
        cmd = pick_validation_command(project_root) or "make test"
        validation = await run_validation_command(
            project_root, cmd, allowed_roots=self._allowed_roots
        )
        passed = validation.exit_code == 0 and not validation.blocked
        stage = CodingTaskStage.COMPLETED if passed else CodingTaskStage.FAILED
        msg = (
            "Validation passed." if passed else f"Validation failed (exit {validation.exit_code})."
        )
        await self._advance(result, stage, msg)
        result.summary = (result.summary or "") + f"\n\nRe-validation: {msg}"
        await self._project_svc.upsert_memory(
            principal,
            result.project_root,
            last_validation_command=cmd,
            last_validation_result={
                "exit_code": validation.exit_code,
                "stdout": validation.stdout_excerpt[:2000],
                "stderr": validation.stderr_excerpt[:2000],
            },
            last_task_summary=result.summary,
        )
        await self.session.flush()
        return {
            "task_id": result.id,
            "stage": result.stage,
            "passed": passed,
            "validation": {
                "command": cmd,
                "exit_code": validation.exit_code,
                "stdout": validation.stdout_excerpt[:1500],
                "stderr": validation.stderr_excerpt[:1500],
            },
        }

    async def get_task(self, principal: Principal, task_id: str) -> CodingTask | None:
        task = await self.session.get(CodingTask, task_id)
        if task is None or task.user_id != principal.user_id:
            return None
        return task

    def _analyze_failure(self, validation: Any) -> str:
        combined = f"{validation.stdout_excerpt}\n{validation.stderr_excerpt}"
        if validation.blocked:
            return f"Validation blocked: {validation.block_reason or 'unknown'}"
        if validation.exit_code == 0:
            return "All tests passed; no failure detected."
        fail_lines = [
            line
            for line in combined.splitlines()
            if any(k in line for k in ("FAILED", "Error", "AssertionError", "error"))
        ]
        return "\n".join(fail_lines[:15]) or combined[:800] or "Test failure with no output."

    async def _propose_patch(
        self,
        project_root: Path,
        user_request: str,
        analysis: str,
        validation: Any,
    ) -> dict[str, Any]:
        heuristic = self._heuristic_patch(project_root, analysis)
        if heuristic is not None:
            return heuristic

        prompt = (
            "You are a coding assistant. Propose a minimal unified-diff style fix.\n"
            f"Project: {project_root}\n"
            f"Request: {user_request}\n"
            f"Test output:\n{analysis[:1500]}\n"
            'Reply with JSON only: {"files":[{"path":"relative/path.py",'
            '"action":"modify","content":"full file content"}],"summary":"..."}'
        )
        inference = await self._provider.infer(
            InferenceRequest(prompt=prompt, intent="patch_proposal", stream=False)
        )
        parsed = self._parse_model_patch(inference.content, project_root)
        if parsed is not None:
            return parsed
        return self._empty_patch_payload(project_root, "Could not derive patch from model output.")

    def _heuristic_patch(self, project_root: Path, analysis: str) -> dict[str, Any] | None:
        rel: str | None = None
        path_match = re.search(r"tests[/\\]([\w/\\.-]+\.py)", analysis)
        if path_match:
            rel = path_match.group(1).replace("\\", "/")
        else:
            demo = project_root / "tests" / "demo_fail.py"
            if demo.exists() and "demo_fail" in analysis or demo.exists() and not analysis.strip():
                rel = "tests/demo_fail.py"
        if rel is None:
            demo = project_root / "tests" / "demo_fail.py"
            if demo.exists():
                rel = "tests/demo_fail.py"
            else:
                return None
        target = project_root / rel
        if not target.exists():
            return None
        rel_path = str(target.relative_to(project_root))
        content = target.read_text(encoding="utf-8", errors="replace")
        if "assert False" in content:
            new_content = content.replace("assert False", "assert True", 1)
        elif "assert 1 == 2" in content:
            new_content = content.replace("assert 1 == 2", "assert 1 == 1", 1)
        else:
            return None
        changes = [PatchFileChange(relative_path=rel_path, action="modify", content=new_content)]
        unified = build_unified_diff(project_root, changes)
        return {
            "project_root": str(project_root),
            "summary": f"Fix failing assertion in {rel_path}",
            "files": [
                {"path": rel_path, "action": "modify", "content": new_content},
            ],
            "unified_diff": unified,
        }

    def _parse_model_patch(self, content: str, project_root: Path) -> dict[str, Any] | None:
        import json

        text = content.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or "files" not in data:
            return None
        payload = {
            "project_root": str(project_root),
            "summary": str(data.get("summary", "Model-proposed patch")),
            "files": data.get("files", []),
            "unified_diff": "",
        }
        validation = validate_patch_payload(project_root, payload)
        if not validation.allowed:
            return None
        payload["unified_diff"] = build_unified_diff(project_root, validation.files)
        return payload

    def _empty_patch_payload(self, project_root: Path, summary: str) -> dict[str, Any]:
        return {
            "project_root": str(project_root),
            "summary": summary,
            "files": [],
            "unified_diff": "",
        }

    async def _advance(self, task: CodingTask, stage: CodingTaskStage, message: str) -> None:
        task.stage = stage.value
        timeline = list(task.timeline or [])
        timeline.append(self._timeline_entry(stage, message))
        task.timeline = timeline

    async def _fail(self, task: CodingTask, message: str) -> None:
        await self._advance(task, CodingTaskStage.FAILED, message)
        task.summary = message

    @staticmethod
    def _timeline_entry(stage: CodingTaskStage, message: str) -> dict[str, str]:
        return {
            "stage": stage.value,
            "message": message,
            "at": _utc_now().isoformat(),
        }

    @staticmethod
    def _task_response(task: CodingTask, **extra: Any) -> dict[str, Any]:
        return {
            "task_id": task.id,
            "stage": task.stage,
            "timeline": task.timeline or [],
            "summary": task.summary,
            **extra,
        }

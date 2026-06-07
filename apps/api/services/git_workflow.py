"""Safe local git workflow — branch create and commit require separate approvals."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.approvals import ApprovalRequestService
from nova_core.auth.principal import Principal
from nova_core.capabilities.model import (
    CapabilityName,
    compute_action_fingerprint,
    risk_for_capability,
)
from nova_core.patch.policy import validate_patch_payload
from nova_core.project.context import validate_project_root
from nova_core.schemas.errors import (
    ConflictError,
    ValidationError,
)
from nova_core.schemas.settings import Settings
from nova_core.sentry.audit import record_audit_event
from nova_core.shell.safe_command import sanitize_output_excerpt, validate_safe_shell_command
from nova_core.tools.protected_paths import is_protected_path

BLOCKED_GIT_PATTERNS: tuple[str, ...] = (
    "push",
    "reset --hard",
    "clean",
    "checkout --",
    "force",
    "remote",
)

VENDOR_DIR_NAMES: frozenset[str] = frozenset(
    {"node_modules", ".venv", "vendor", "dist", "build", "__pycache__"}
)


@dataclass(frozen=True)
class GitProposal:
    branch_name: str
    commit_message: str
    staged_paths: list[str]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sanitize_branch_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9/_-]", "-", name.strip())[:64]
    return cleaned or "nova/branch"


def _validate_staged_paths(project_root: Path, paths: list[str]) -> tuple[bool, str | None]:
    if not paths:
        return False, "No staged paths specified"
    for rel in paths:
        if ".." in rel or rel.startswith("/"):
            return False, f"Invalid path: {rel}"
        full = (project_root / rel).resolve()
        try:
            full.relative_to(project_root.resolve())
        except ValueError:
            return False, f"Path outside project: {rel}"
        if is_protected_path(str(full)):
            return False, f"Protected path cannot be staged: {rel}"
        parts = Path(rel).parts
        if any(p in VENDOR_DIR_NAMES for p in parts):
            return False, f"Vendor/generated path blocked: {rel}"
    return True, None


class GitWorkflowService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        policies = settings.load_yaml("policies.yaml")
        safe_cfg = policies.get("safe_filesystem", {})
        self._allowed_roots = safe_cfg.get("allowed_roots") if isinstance(safe_cfg, dict) else None
        self._approval_svc = ApprovalRequestService(session, settings)

    async def git_status(self, principal: Principal, project_root: str) -> dict[str, Any]:
        root = self._resolve_root(project_root)
        out = self._run_git(root, "git status")
        return {"project_root": str(root), "status": out}

    async def git_diff_stat(self, principal: Principal, project_root: str) -> dict[str, Any]:
        root = self._resolve_root(project_root)
        out = self._run_git(root, "git diff --stat")
        return {"project_root": str(root), "diff_stat": out}

    async def propose_branch(
        self,
        principal: Principal,
        *,
        project_root: str,
        branch_name: str,
    ) -> dict[str, Any]:
        root = self._resolve_root(project_root)
        branch = _sanitize_branch_name(branch_name)
        payload = {"project_root": str(root), "branch_name": branch}
        preview = f"Create local branch: {branch}\nProject: {root}\nPush: DISABLED"
        approval = await self._approval_svc.create_request(
            principal,
            capability=CapabilityName.GIT_BRANCH_CREATE,
            action_summary=f"Create branch {branch}",
            preview=preview,
            payload=payload,
            risk_level=risk_for_capability(CapabilityName.GIT_BRANCH_CREATE),
        )
        return {
            "approval_id": approval.id,
            "branch_name": branch,
            "fingerprint": approval.action_fingerprint,
            "push_disabled": True,
        }

    async def create_approved_branch(
        self, principal: Principal, approval_id: str
    ) -> dict[str, Any]:
        record = await self._approval_svc.consume_for_execution(
            principal, approval_id, CapabilityName.GIT_BRANCH_CREATE
        )
        payload = (record.metadata_json or {}).get("payload") or {}
        root = self._resolve_root(str(payload.get("project_root", "")))
        branch = str(payload.get("branch_name", ""))
        fp = compute_action_fingerprint(CapabilityName.GIT_BRANCH_CREATE.value, payload)
        if fp != record.action_fingerprint:
            raise ConflictError("Branch approval fingerprint mismatch")
        self._assert_git_allowed(f"git checkout -b {branch}")
        proc = subprocess.run(
            ["git", "checkout", "-b", branch],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise ValidationError(sanitize_output_excerpt((proc.stderr or proc.stdout or "")[:500]))
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action="git.branch.created",
            resource_type="approval_request",
            resource_id=approval_id,
            details={"branch": branch, "project_root": str(root)},
        )
        return {"branch_name": branch, "project_root": str(root), "push_disabled": True}

    async def propose_commit(
        self,
        principal: Principal,
        *,
        project_root: str,
        commit_message: str,
        staged_paths: list[str],
    ) -> dict[str, Any]:
        root = self._resolve_root(project_root)
        ok, reason = _validate_staged_paths(root, staged_paths)
        if not ok:
            raise ValidationError(reason or "Invalid staged paths")
        message = commit_message.strip()[:500]
        if not message:
            raise ValidationError("Commit message required")
        payload = {
            "project_root": str(root),
            "commit_message": message,
            "staged_paths": staged_paths,
        }
        preview = (
            f"Local commit\nMessage: {message}\nFiles: {', '.join(staged_paths)}\nPush: DISABLED"
        )
        approval = await self._approval_svc.create_request(
            principal,
            capability=CapabilityName.GIT_COMMIT,
            action_summary=f"Commit: {message[:80]}",
            preview=preview,
            payload=payload,
            risk_level=risk_for_capability(CapabilityName.GIT_COMMIT),
        )
        return {
            "approval_id": approval.id,
            "commit_message": message,
            "staged_paths": staged_paths,
            "fingerprint": approval.action_fingerprint,
            "push_disabled": True,
        }

    async def commit_approved(self, principal: Principal, approval_id: str) -> dict[str, Any]:
        record = await self._approval_svc.consume_for_execution(
            principal, approval_id, CapabilityName.GIT_COMMIT
        )
        payload = (record.metadata_json or {}).get("payload") or {}
        root = self._resolve_root(str(payload.get("project_root", "")))
        message = str(payload.get("commit_message", ""))
        staged_paths = list(payload.get("staged_paths") or [])
        fp = compute_action_fingerprint(CapabilityName.GIT_COMMIT.value, payload)
        if fp != record.action_fingerprint:
            raise ConflictError("Commit approval fingerprint mismatch")
        ok, reason = _validate_staged_paths(root, staged_paths)
        if not ok:
            raise ValidationError(reason or "Invalid staged paths")
        for rel in staged_paths:
            stage_proc = subprocess.run(
                ["git", "add", rel],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if stage_proc.returncode != 0:
                raise ValidationError(sanitize_output_excerpt((stage_proc.stderr or "")[:300]))
        commit_proc = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if commit_proc.returncode != 0:
            raise ValidationError(
                sanitize_output_excerpt((commit_proc.stderr or commit_proc.stdout or "")[:500])
            )
        log_out = self._run_git(root, "git log --oneline -n 3")
        await record_audit_event(
            self.session,
            actor_type="device",
            actor_id=principal.device_id or principal.user_id,
            action="git.commit.created",
            resource_type="approval_request",
            resource_id=approval_id,
            details={"message": message[:100], "files": staged_paths},
        )
        return {
            "commit_message": message,
            "staged_paths": staged_paths,
            "log": log_out,
            "push_disabled": True,
        }

    async def git_push_blocked(self, principal: Principal) -> dict[str, Any]:
        _ = principal
        return {
            "blocked": True,
            "reason": "git.push is permanently blocked by NOVA policy",
        }

    def _resolve_root(self, project_root: str) -> Path:
        validation = validate_project_root(project_root, allowed_roots=self._allowed_roots)
        if not validation.allowed or validation.resolved is None:
            raise ValidationError(validation.reason or "Project root blocked")
        return validation.resolved

    def _run_git(self, project_root: Path, command: str) -> str:
        self._assert_git_allowed(command)
        validation = validate_safe_shell_command(command, allowed_roots=self._allowed_roots)
        if not validation.allowed or validation.argv is None:
            return validation.reason or "blocked"
        try:
            proc = subprocess.run(
                validation.argv,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            combined = (proc.stdout or "") + (proc.stderr or "")
            return sanitize_output_excerpt(combined, max_length=2000)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"error: {exc}"

    @staticmethod
    def _assert_git_allowed(command: str) -> None:
        lowered = command.lower()
        for pattern in BLOCKED_GIT_PATTERNS:
            if pattern in lowered:
                raise ValidationError(f"Git command blocked: {pattern}")

    @staticmethod
    def validate_patch_paths_for_commit(project_root: Path, payload: dict[str, Any]) -> bool:
        validation = validate_patch_payload(project_root, payload)
        return validation.allowed

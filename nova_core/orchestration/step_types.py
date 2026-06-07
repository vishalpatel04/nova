"""Allowlisted orchestration step types and plan templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nova_core.models.enums import OrchestrationRole

DEFAULT_MAX_STEPS = 8
MAX_RETRIES_PER_STEP = 2

ALLOWED_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "project.inspect",
        "project.read_safe_file",
        "project.run_validation",
        "patch.propose",
        "patch.review",
        "patch.await_approval",
        "patch.apply_approved",
        "project.rerun_validation",
        "git.diff_stat",
        "git.status",
        "git.commit_propose",
        "report.final",
    }
)

_ROLE_FOR_ACTION: dict[str, OrchestrationRole] = {
    "project.inspect": OrchestrationRole.INSPECTOR,
    "project.read_safe_file": OrchestrationRole.INSPECTOR,
    "project.run_validation": OrchestrationRole.VALIDATOR,
    "project.rerun_validation": OrchestrationRole.VALIDATOR,
    "patch.propose": OrchestrationRole.CODER,
    "patch.review": OrchestrationRole.REVIEWER,
    "patch.await_approval": OrchestrationRole.REVIEWER,
    "patch.apply_approved": OrchestrationRole.CODER,
    "git.diff_stat": OrchestrationRole.INSPECTOR,
    "git.status": OrchestrationRole.INSPECTOR,
    "git.commit_propose": OrchestrationRole.REPORTER,
    "report.final": OrchestrationRole.REPORTER,
}


@dataclass(frozen=True)
class PlanStepSpec:
    step_index: int
    agent_role: str
    action_type: str
    input_summary: str


def validate_step_action(action_type: str) -> tuple[bool, str | None]:
    if action_type not in ALLOWED_ACTION_TYPES:
        return False, f"Unsupported action type: {action_type}"
    return True, None


def role_for_action(action_type: str) -> OrchestrationRole:
    return _ROLE_FOR_ACTION.get(action_type, OrchestrationRole.INSPECTOR)


def build_default_repair_plan(*, objective: str) -> list[dict[str, Any]]:
    """Deterministic bounded repair workflow (max 8 steps)."""
    specs = [
        PlanStepSpec(
            0,
            OrchestrationRole.INSPECTOR.value,
            "project.inspect",
            "Inspect repo structure",
        ),
        PlanStepSpec(
            1,
            OrchestrationRole.INSPECTOR.value,
            "project.run_validation",
            "Run validation to capture failure evidence",
        ),
        PlanStepSpec(
            2,
            OrchestrationRole.CODER.value,
            "patch.propose",
            f"Propose minimal patch for: {objective[:120]}",
        ),
        PlanStepSpec(
            3,
            OrchestrationRole.REVIEWER.value,
            "patch.review",
            "Independent review of proposed patch",
        ),
        PlanStepSpec(
            4,
            OrchestrationRole.REVIEWER.value,
            "patch.await_approval",
            "Wait for user patch approval",
        ),
        PlanStepSpec(
            5,
            OrchestrationRole.VALIDATOR.value,
            "project.rerun_validation",
            "Re-run validation after patch apply",
        ),
        PlanStepSpec(
            6,
            OrchestrationRole.REPORTER.value,
            "git.commit_propose",
            "Propose branch and commit after successful validation",
        ),
        PlanStepSpec(
            7,
            OrchestrationRole.REPORTER.value,
            "report.final",
            "Final human-readable summary",
        ),
    ]
    if len(specs) > DEFAULT_MAX_STEPS:
        raise ValueError(f"Plan exceeds max steps ({DEFAULT_MAX_STEPS})")
    return [
        {
            "step_index": s.step_index,
            "agent_role": s.agent_role,
            "action_type": s.action_type,
            "input_summary": s.input_summary,
        }
        for s in specs
    ]

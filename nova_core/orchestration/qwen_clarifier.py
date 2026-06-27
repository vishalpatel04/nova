"""Qwen-assisted structured app-build clarification with safe fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from nova_core.forge.selector import suggest_forge_engine
from nova_core.orchestration.app_request import AppRequest
from nova_core.orchestration.app_spec import build_app_spec
from nova_core.orchestration.app_spec_clarification import (
    build_clarification_message,
    build_spec_preview,
    default_assumptions,
)
from nova_core.providers.runtime import InferenceRequest, ProviderRuntime
from nova_core.schemas.settings import Settings

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


class ClarificationPlan(BaseModel):
    app_type: str
    inferred_goal: str = ""
    inferred_audience: str = ""
    inferred_style: str = ""
    inferred_features: list[str] = Field(default_factory=list)
    missing_critical_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    safe_assumptions: list[str] = Field(default_factory=list)
    proceed_with_confirmation: bool = False
    confirmation_message: str = ""
    opening_line: str = ""

    @field_validator("questions")
    @classmethod
    def _cap_questions(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        return cleaned[:4]

    @field_validator("safe_assumptions")
    @classmethod
    def _cap_assumptions(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        return cleaned[:6]


def has_explicit_name(request: AppRequest) -> bool:
    raw = request.raw_user_request.lower()
    return (
        " named " in raw
        or " called " in raw
        or raw.startswith("named ")
        or raw.startswith("called ")
    )


def should_quick_confirm(request: AppRequest) -> bool:
    if request.requires_clarification:
        return False
    if request.app_type == "landing_page":
        return False
    if not has_explicit_name(request):
        return False
    return request.app_type in {
        "todo",
        "habit_tracker",
        "expense_tracker",
    }


def deterministic_plan(request: AppRequest) -> ClarificationPlan:
    assumptions = default_assumptions(request)
    if should_quick_confirm(request):
        features = ", ".join(request.features) if request.features else "core MVP features"
        return ClarificationPlan(
            app_type=request.app_type,
            inferred_goal=f"Simple {request.app_type.replace('_', ' ')} for {request.app_name}",
            inferred_features=list(request.features),
            safe_assumptions=assumptions,
            proceed_with_confirmation=True,
            confirmation_message=(
                f"Got it. I'll build {request.app_name} with {features} and localStorage. Proceed?"
            ),
            opening_line=f"Got it — {request.app_name}.",
        )
    from nova_core.orchestration.app_spec_clarification import clarification_questions

    return ClarificationPlan(
        app_type=request.app_type,
        inferred_goal=assumptions[0] if assumptions else "product discovery and conversion",
        inferred_audience=assumptions[0].split(":", 1)[-1].strip() if assumptions else "",
        inferred_style="clean, premium, modern",
        inferred_features=list(request.features),
        missing_critical_fields=["audience", "tone", "cta"],
        questions=clarification_questions(request),
        safe_assumptions=assumptions,
        opening_line="I can build that.",
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            pass
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _build_qwen_prompt(request: AppRequest) -> str:
    spec = build_app_spec(request)
    return (
        "You are NOVA Prime planning an Agent OS app build. "
        "Return ONLY valid JSON matching this schema:\n"
        "{"
        '"app_type": "string", '
        '"inferred_goal": "string", '
        '"inferred_audience": "string", '
        '"inferred_style": "string", '
        '"inferred_features": ["string"], '
        '"missing_critical_fields": ["string"], '
        '"questions": ["string"], '
        '"safe_assumptions": ["string"], '
        '"proceed_with_confirmation": false, '
        '"confirmation_message": "string", '
        '"opening_line": "string"'
        "}\n"
        "Rules:\n"
        "- Ask 2-4 high-value questions only when critical info is missing.\n"
        "- If the request is specific with a named app (todo/calculator/etc.), set "
        "proceed_with_confirmation=true and a short confirmation_message; questions=[].\n"
        "- For vague landing pages or ambiguous AI apps, ask context-specific questions.\n"
        "- Never include markdown or prose outside JSON.\n\n"
        f"User request: {request.raw_user_request}\n"
        f"Parsed app_type: {request.app_type}\n"
        f"Parsed app_name: {request.app_name}\n"
        f"Parsed runtime: {request.runtime}\n"
        f"Default features: {list(request.features)}\n"
        f"Template components: {list(spec.components)}\n"
    )


async def generate_clarification_plan(
    settings: Settings,
    request: AppRequest,
) -> ClarificationPlan:
    runtime = ProviderRuntime(settings)
    prompt = _build_qwen_prompt(request)
    try:
        result = await runtime.infer_reasoning_lane(
            InferenceRequest(
                prompt=prompt,
                system_prompt=(
                    "You output strict JSON only for NOVA Agent OS clarification planning."
                ),
                intent="app_spec_clarification",
            ),
            purpose="reasoning",
        )
        if result.error or not result.content.strip():
            return deterministic_plan(request)
        payload = _extract_json_object(result.content)
        if payload is None:
            return deterministic_plan(request)
        plan = ClarificationPlan.model_validate(payload)
        if plan.proceed_with_confirmation:
            plan.questions = []
        elif len(plan.questions) < 2:
            fallback = deterministic_plan(request)
            plan.questions = fallback.questions or plan.questions
        if not plan.safe_assumptions:
            plan.safe_assumptions = default_assumptions(request)
        return plan
    except Exception:
        return deterministic_plan(request)


def _forge_engine_clarification_block(request: AppRequest) -> list[str]:
    suggestion = suggest_forge_engine(request.raw_user_request)
    if suggestion.complexity != "complex" and not suggestion.suggest_external:
        return []
    lines = [
        "",
        f"Complexity: {suggestion.complexity}",
        "This may exceed template scaffolding (auth/database/backend).",
        suggestion.reason,
        "Forge can delegate to OpenHands, Claude Code, Codex, or Cursor when configured.",
    ]
    if suggestion.suggest_external:
        lines.append(
            "Reply with your preferred engine, or say use deterministic fallback "
            "for template scaffold."
        )
    return lines


def format_clarification_message(request: AppRequest, plan: ClarificationPlan) -> str:
    if plan.proceed_with_confirmation and plan.confirmation_message:
        return (
            f"{plan.confirmation_message}\n\n"
            "Reply **yes** to build, **no** to cancel, or add tweaks."
        )
    preview = build_spec_preview(request)
    opening = plan.opening_line.strip() or "I can build that."
    lines = [opening, "", "Quick spec:", "", *preview]
    if plan.inferred_goal and plan.inferred_goal not in preview[2]:
        lines.extend(["", f"Assumed goal: {plan.inferred_goal}"])
    if plan.questions:
        lines.extend(["", "Quick questions:", ""])
        for index, question in enumerate(plan.questions, start=1):
            lines.append(f"{index}. {question}")
    lines.extend(_forge_engine_clarification_block(request))
    lines.extend(
        [
            "",
            'Reply with answers, or say "use your best assumptions".',
        ]
    )
    return "\n".join(lines)


async def build_clarification_message_async(
    settings: Settings,
    request: AppRequest,
) -> tuple[str, ClarificationPlan]:
    plan = await generate_clarification_plan(settings, request)
    if plan.proceed_with_confirmation and plan.confirmation_message:
        return format_clarification_message(request, plan), plan
    if not plan.questions:
        return build_clarification_message(request), plan
    return format_clarification_message(request, plan), plan

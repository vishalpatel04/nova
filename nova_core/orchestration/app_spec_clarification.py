"""App-build spec preview and clarification for conversational Agent OS."""

from __future__ import annotations

from nova_core.orchestration.app_request import DEFAULT_DISPLAY_NAMES, AppRequest
from nova_core.orchestration.app_spec import build_app_spec

ASSUMPTION_PHRASES: tuple[str, ...] = (
    "use your best assumptions",
    "use best assumptions",
    "use defaults",
    "go ahead",
    "just build it",
    "proceed",
    "build it",
)

APP_TYPE_LABELS: dict[str, str] = {
    "calculator": "Calculator",
    "cli_calculator": "CLI calculator",
    "todo": "Todo app",
    "habit_tracker": "Habit tracker",
    "expense_tracker": "Expense tracker",
    "landing_page": "Landing page",
    "generic": "Web app",
}


def is_assumption_continuation(text: str) -> bool:
    lowered = text.lower().strip().rstrip(".")
    if lowered in ASSUMPTION_PHRASES:
        return True
    return any(phrase in lowered for phrase in ASSUMPTION_PHRASES)


def is_vague_app_request(request: AppRequest) -> bool:
    if request.requires_clarification:
        return True
    if request.app_type == "landing_page":
        return True
    if request.app_type in {"todo", "habit_tracker", "expense_tracker", "generic"}:
        defaults = set(DEFAULT_DISPLAY_NAMES.values()) | {
            "NOVA Todo",
            "NOVA Habit Tracker",
            "NOVA Expense Tracker",
            "NOVA App",
        }
        if request.app_name in defaults:
            return True
    return False


def _brand_context(app_name: str) -> dict[str, str]:
    lowered = app_name.lower()
    if "susco" in lowered:
        return {
            "goal": "sustainability shopping and product discovery",
            "style": "clean, premium, green/sustainable",
            "tone": "serious investor tone with consumer clarity",
            "cta": "Shop sustainably",
            "audience": "eco-conscious shoppers and retail partners",
        }
    return {
        "goal": "product discovery and conversion",
        "style": "clean, premium, modern",
        "tone": "professional and approachable",
        "cta": "Get started",
        "audience": "early adopters and decision makers",
    }


def default_assumptions(request: AppRequest) -> list[str]:
    brand = _brand_context(request.app_name)
    if request.app_type == "landing_page":
        return [
            f"Target user: {brand['audience']}",
            f"Main CTA: {brand['cta']}",
            f"Tone: {brand['tone']}",
            f"Style: {brand['style']}",
        ]
    if request.app_type == "todo":
        return [
            "Target user: busy professionals tracking daily tasks",
            "Features: add, complete, delete, filter active/completed",
            "Persistence: localStorage with demo seed tasks",
        ]
    if request.app_type == "habit_tracker":
        return [
            "Target user: people building daily routines",
            "Features: streaks, weekly grid, mark complete",
            "Persistence: localStorage with sample habits",
        ]
    if request.app_type == "expense_tracker":
        return [
            "Target user: individuals tracking personal spending",
            "Features: income/expense entries, categories, balance",
            "Persistence: localStorage with sample transactions",
        ]
    return [
        "Target user: demo users evaluating the product",
        "Scope: polished MVP suitable for investor preview",
        "Style: modern responsive UI",
    ]


def clarification_questions(request: AppRequest) -> list[str]:
    if request.app_type == "landing_page":
        return [
            "Who is the target user?",
            "What should the main CTA say?",
            "Do you want a serious investor tone or consumer-friendly tone?",
        ]
    if request.app_type == "todo":
        return [
            "Who is this todo app for?",
            "Should it include filters and demo seed tasks?",
        ]
    if request.requires_clarification:
        return [
            "Should this be a CLI app or a web app?",
            "What core features matter most?",
        ]
    return [
        f"What is the primary goal for {request.app_name}?",
        "Any must-have features before I build?",
    ]


def build_spec_preview(request: AppRequest) -> list[str]:
    spec = build_app_spec(request)
    brand = _brand_context(request.app_name)
    app_label = APP_TYPE_LABELS.get(request.app_type, request.app_type)
    lines = [
        f"• App type: {app_label}",
        f"• Brand: {request.app_name}",
        f"• Goal: {brand['goal']}",
        f"• Sections: {', '.join(spec.components)}",
        f"• Style: {brand['style']}",
        f"• Output: {spec.stack} with local preview",
    ]
    return lines


def build_clarification_message(request: AppRequest) -> str:
    preview = build_spec_preview(request)
    questions = clarification_questions(request)
    lines = [
        "I can build that. Quick spec:",
        "",
        *preview,
        "",
        "A few quick questions:",
        "",
    ]
    for index, question in enumerate(questions, start=1):
        lines.append(f"{index}. {question}")
    lines.extend(
        [
            "",
            'Reply with answers, or say "use your best assumptions".',
        ]
    )
    return "\n".join(lines)


def merge_request_with_answers(
    raw_request: str,
    request: AppRequest,
    user_reply: str,
    *,
    use_assumptions: bool,
) -> tuple[str, list[str]]:
    assumptions = default_assumptions(request)
    if use_assumptions:
        note = "Assumptions: " + "; ".join(assumptions)
    else:
        cleaned = user_reply.strip()
        assumptions = [line.strip() for line in cleaned.split("\n") if line.strip()]
        if len(assumptions) == 1 and not assumptions[0].endswith("."):
            assumptions = [cleaned]
        note = "User guidance: " + "; ".join(assumptions)
    enhanced = f"{raw_request.strip()}\n\n{note}"
    return enhanced, assumptions

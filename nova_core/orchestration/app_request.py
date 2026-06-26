"""Parse natural-language app build requests."""

from __future__ import annotations

import re
from dataclasses import dataclass

APP_BUILD_VERBS = r"(?:build|create|make)"

APP_TYPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "calculator",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?calculator(?:\s+app)?",
        ),
    ),
    (
        "todo",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?todo(?:\s+app)?",
        ),
    ),
    (
        "habit_tracker",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?habit[\s-]?tracker(?:\s+app)?",
        ),
    ),
    (
        "expense_tracker",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:an?\s+)?expense[\s-]?tracker(?:\s+app)?",
        ),
    ),
    (
        "landing_page",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?landing\s+page(?:\s+for\s+(?P<name>.+))?",
        ),
    ),
    (
        "generic",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?simple\s+web\s+app\s+for\s+(?P<idea>.+)",
        ),
    ),
    (
        "generic",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?web\s+app\s+for\s+(?P<idea>.+)",
        ),
    ),
)


@dataclass(frozen=True)
class AppRequest:
    raw_user_request: str
    app_type: str
    app_name: str
    features: tuple[str, ...]
    style_preference: str
    deployment_requested: bool
    requires_clarification: bool


def _default_features(app_type: str) -> tuple[str, ...]:
    features: dict[str, tuple[str, ...]] = {
        "calculator": ("arithmetic", "clear", "decimal", "divide-by-zero", "keyboard"),
        "todo": ("add", "complete", "delete", "filter", "localStorage"),
        "habit_tracker": ("add_habit", "mark_complete", "streak", "weekly_grid", "localStorage"),
        "expense_tracker": (
            "income_expense",
            "category",
            "balance",
            "transactions",
            "localStorage",
        ),
        "landing_page": ("hero", "features", "how_it_works", "cta", "responsive"),
        "generic": ("placeholder_ui", "responsive", "readme"),
    }
    return features.get(app_type, ("placeholder_ui",))


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "nova-app"


def parse_app_request(text: str) -> AppRequest | None:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return None

    lowered = normalized.lower()
    deployment_requested = any(
        token in lowered for token in ("deploy", "deployment", "ship", "publish")
    )

    for app_type, pattern in APP_TYPE_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue

        app_name = {
            "calculator": "NOVA Calculator",
            "todo": "NOVA Todo",
            "habit_tracker": "NOVA Habit Tracker",
            "expense_tracker": "NOVA Expense Tracker",
        }.get(app_type, "NOVA App")

        if app_type == "landing_page":
            custom = (match.groupdict().get("name") or "").strip().rstrip("?.,")
            app_name = f"{custom} Landing Page" if custom else "Startup Landing Page"

        if app_type == "generic":
            idea = (match.groupdict().get("idea") or "").strip().rstrip("?.,")
            app_name = idea[:80] if idea else "Custom Web App"

        return AppRequest(
            raw_user_request=normalized,
            app_type=app_type,
            app_name=app_name,
            features=_default_features(app_type),
            style_preference="modern",
            deployment_requested=deployment_requested,
            requires_clarification=False,
        )

    if re.search(rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?(?:simple\s+)?web\s+app", normalized):
        return AppRequest(
            raw_user_request=normalized,
            app_type="generic",
            app_name="Custom Web App",
            features=_default_features("generic"),
            style_preference="modern",
            deployment_requested=deployment_requested,
            requires_clarification=False,
        )

    return None


def is_app_build_request(text: str) -> bool:
    return parse_app_request(text) is not None


def project_dir_name(app_request: AppRequest) -> str:
    mapping = {
        "calculator": "calculator-app",
        "todo": "todo-app",
        "habit_tracker": "habit-tracker-app",
        "expense_tracker": "expense-tracker-app",
    }
    if app_request.app_type in mapping:
        return mapping[app_request.app_type]
    if app_request.app_type == "landing_page":
        slug = _slugify(app_request.app_name.replace(" Landing Page", ""))
        return f"landing-page-{slug}"
    slug = _slugify(app_request.app_name)
    return f"web-app-{slug}"

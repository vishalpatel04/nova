"""Parse natural-language app build requests."""

from __future__ import annotations

import re
from dataclasses import dataclass

APP_BUILD_VERBS = r"(?:build|create|make)"
CUSTOM_NAME = r"(?P<custom>[A-Za-z][A-Za-z0-9_-]*)"
TRAILING = r"(?:\s*$|[?.!,])"

# Broad intent detector — routes to Agent OS before Qwen even when parse needs clarification.
APP_BUILD_INTENT_RE = re.compile(
    rf"(?i){APP_BUILD_VERBS}\s+(?:me\s+)?(?:a\s+)?(?:[\w-]+\s+)*?"
    r"(?:calculator|todo|habit[\s-]?tracker|expense[\s-]?tracker|landing\s+page|crm|"
    r"web\s+app|an?\s+app\b|virat\s+kohli|kohli.*test\s+stats|test\s+stats.*kohli)"
)

# Ordered from most specific to least specific.
PARSE_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "cli_calculator",
        "cli",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?(?:simple\s+)?command-?line\s+"
            rf"calculator(?:\s+app)?\s+(?:named|called)\s+{CUSTOM_NAME}{TRAILING}"
        ),
    ),
    (
        "calculator",
        "web",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?(?:simple\s+)?calculator(?:\s+app)?\s+"
            rf"(?:named|called)\s+{CUSTOM_NAME}{TRAILING}"
        ),
    ),
    (
        "calculator",
        "web",
        re.compile(rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?calculator(?:\s+app)?{TRAILING}"),
    ),
    (
        "todo",
        "web",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?todo(?:\s+app)?\s+"
            rf"(?:named|called)\s+{CUSTOM_NAME}{TRAILING}"
        ),
    ),
    (
        "todo",
        "web",
        re.compile(rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?todo(?:\s+app)?{TRAILING}"),
    ),
    (
        "habit_tracker",
        "web",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?habit[\s-]?tracker(?:\s+app)?\s+"
            rf"(?:named|called)\s+{CUSTOM_NAME}{TRAILING}"
        ),
    ),
    (
        "habit_tracker",
        "web",
        re.compile(rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?habit[\s-]?tracker(?:\s+app)?{TRAILING}"),
    ),
    (
        "expense_tracker",
        "web",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:an?\s+)?expense[\s-]?tracker(?:\s+app)?\s+"
            rf"(?:named|called)\s+{CUSTOM_NAME}{TRAILING}"
        ),
    ),
    (
        "expense_tracker",
        "web",
        re.compile(rf"(?i){APP_BUILD_VERBS}\s+(?:an?\s+)?(?:proper\s+)?expense[\s-]?tracker\b.*"),
    ),
    (
        "expense_tracker",
        "web",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:an?\s+)?expense[\s-]?tracker(?:\s+app)?{TRAILING}"
        ),
    ),
    (
        "generic",
        "web",
        re.compile(rf"(?i){APP_BUILD_VERBS}\s+(?:an?\s+)?crm\b.*"),
    ),
    (
        "landing_page",
        "web",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?landing\s+page\s+"
            rf"(?:named|called|for)\s+(?P<custom>.+?){TRAILING}"
        ),
    ),
    (
        "landing_page",
        "web",
        re.compile(rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?landing\s+page{TRAILING}"),
    ),
    (
        "kohli_stats",
        "web",
        re.compile(
            rf"(?i)(?:{APP_BUILD_VERBS}\s+(?:a\s+)?(?:page|dashboard)\s+(?:on|about|for)\s+)?"
            r"virat\s+kohli(?:\s+test\s+stats)?{TRAILING}"
        ),
    ),
    (
        "kohli_stats",
        "web",
        re.compile(rf"(?i).*\b(?:virat\s+kohli|\bkohli\b)\b.*test\s+stats{TRAILING}"),
    ),
    (
        "generic",
        "web",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?simple\s+web\s+app\s+for\s+(?P<custom>.+?){TRAILING}"
        ),
    ),
    (
        "generic",
        "web",
        re.compile(
            rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?web\s+app\s+for\s+(?P<custom>.+?){TRAILING}"
        ),
    ),
    (
        "generic",
        "web",
        re.compile(rf"(?i)make\s+me\s+a\s+web\s+app\s+named\s+(?P<custom>.+?){TRAILING}"),
    ),
    (
        "generic",
        "web",
        re.compile(rf"(?i){APP_BUILD_VERBS}\s+an?\s+app\s+named\s+(?P<custom>.+?){TRAILING}"),
    ),
    (
        "generic",
        "web",
        re.compile(rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?(?:simple\s+)?web\s+app{TRAILING}"),
    ),
)

CLI_AMBIGUOUS_RE = re.compile(
    rf"(?i){APP_BUILD_VERBS}\s+(?:a\s+)?(?:simple\s+)?command-?line\s+(?:app|application)\b"
    rf"(?!.*calculator)"
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
    runtime: str = "web"
    clarification_message: str = ""


DEFAULT_DISPLAY_NAMES: dict[str, str] = {
    "calculator": "NOVA Calculator",
    "cli_calculator": "CLI Calculator",
    "todo": "NOVA Todo",
    "habit_tracker": "NOVA Habit Tracker",
    "expense_tracker": "NOVA Expense Tracker",
    "kohli_stats": "Virat Kohli Test Stats",
}


def _default_features(app_type: str) -> tuple[str, ...]:
    features: dict[str, tuple[str, ...]] = {
        "calculator": ("arithmetic", "clear", "decimal", "divide-by-zero", "keyboard"),
        "cli_calculator": ("arithmetic", "repl", "divide-by-zero"),
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
        "kohli_stats": ("headline", "stat_cards", "stats_table", "sample_data"),
        "generic": ("placeholder_ui", "responsive", "readme"),
    }
    return features.get(app_type, ("placeholder_ui",))


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "nova-app"


def _clean_custom_name(value: str) -> str:
    return value.strip().rstrip("?.!,")


def _display_name(app_type: str, custom: str | None) -> str:
    if custom:
        if app_type == "landing_page":
            return f"{custom} Landing Page"
        if app_type == "kohli_stats":
            return "Virat Kohli Test Stats"
        if app_type in {
            "calculator",
            "cli_calculator",
            "todo",
            "habit_tracker",
            "expense_tracker",
            "generic",
        }:
            return custom
        return f"{custom} {DEFAULT_DISPLAY_NAMES.get(app_type, 'App').replace('NOVA ', '')}"
    return DEFAULT_DISPLAY_NAMES.get(app_type, "NOVA App")


def parse_app_request(text: str) -> AppRequest | None:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return None

    lowered = normalized.lower()
    deployment_requested = any(
        token in lowered for token in ("deploy", "deployment", "ship", "publish")
    )

    if CLI_AMBIGUOUS_RE.search(normalized):
        return AppRequest(
            raw_user_request=normalized,
            app_type="generic",
            app_name="App",
            features=(),
            style_preference="modern",
            deployment_requested=deployment_requested,
            requires_clarification=True,
            runtime="unspecified",
            clarification_message=(
                "Do you want a terminal CLI app or a web app?\n"
                "Reply with for example:\n"
                "- create a command-line calculator app named <name>\n"
                "- create a calculator app named <name>"
            ),
        )

    for app_type, runtime, pattern in PARSE_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        custom = match.groupdict().get("custom")
        custom_name = _clean_custom_name(custom) if custom else None
        return AppRequest(
            raw_user_request=normalized,
            app_type=app_type,
            app_name=_display_name(app_type, custom_name),
            features=_default_features(app_type),
            style_preference="modern",
            deployment_requested=deployment_requested,
            requires_clarification=False,
            runtime=runtime,
        )

    return None


def is_app_build_intent(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return False
    if parse_app_request(normalized) is not None:
        return True
    return APP_BUILD_INTENT_RE.search(normalized) is not None


def is_app_build_request(text: str) -> bool:
    return is_app_build_intent(text)


def project_dir_name(app_request: AppRequest) -> str:
    slug = _slugify(app_request.app_name.replace(" Landing Page", ""))
    if app_request.app_type == "calculator":
        default = app_request.app_name == DEFAULT_DISPLAY_NAMES["calculator"]
        return "calculator-app" if default else f"{slug}-calculator-app"
    if app_request.app_type == "cli_calculator":
        return f"{slug}-cli-calculator"
    if app_request.app_type == "todo":
        default = app_request.app_name == DEFAULT_DISPLAY_NAMES["todo"]
        return "todo-app" if default else f"{slug}-todo-app"
    if app_request.app_type == "habit_tracker":
        default = app_request.app_name == DEFAULT_DISPLAY_NAMES["habit_tracker"]
        return "habit-tracker-app" if default else f"{slug}-habit-tracker-app"
    if app_request.app_type == "expense_tracker":
        default = app_request.app_name == DEFAULT_DISPLAY_NAMES["expense_tracker"]
        return "expense-tracker-app" if default else f"{slug}-expense-tracker-app"
    if app_request.app_type == "landing_page":
        return f"landing-page-{slug}"
    if app_request.app_type == "kohli_stats":
        return "virat-kohli-test-stats"
    return f"{slug}-web-app"

"""App spec generation from parsed requests."""

from __future__ import annotations

from dataclasses import dataclass

from nova_core.orchestration.app_request import AppRequest

STACK_WEB = "Vite + React + TypeScript"
STACK_CLI = "Python CLI"


@dataclass(frozen=True)
class AppSpec:
    title: str
    description: str
    stack: str
    pages: tuple[str, ...]
    components: tuple[str, ...]
    user_interactions: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    template_id: str
    app_type: str
    app_name: str


def template_id_for_app_type(app_type: str) -> str:
    mapping = {
        "calculator": "calculator_react_vite",
        "cli_calculator": "cli_calculator_python",
        "todo": "todo_react_vite",
        "habit_tracker": "habit_tracker_react_vite",
        "expense_tracker": "expense_tracker_react_vite",
        "landing_page": "landing_page_react_vite",
        "kohli_stats": "kohli_stats_react_vite",
        "generic": "generic_react_vite",
    }
    return mapping.get(app_type, "generic_react_vite")


def build_app_spec(request: AppRequest) -> AppSpec:
    template_id = template_id_for_app_type(request.app_type)
    stack = STACK_CLI if request.runtime == "cli" else STACK_WEB
    descriptions = {
        "calculator": "Responsive calculator with arithmetic, clear/delete, and keyboard support.",
        "cli_calculator": "Command-line calculator with arithmetic and divide-by-zero handling.",
        "todo": "Task list with add, complete, delete, filters, and localStorage persistence.",
        "habit_tracker": "Habit tracker with streaks, weekly grid, and localStorage persistence.",
        "expense_tracker": "Income/expense tracker with categories, balance, and localStorage.",
        "landing_page": f"Polished landing page for {request.app_name}.",
        "kohli_stats": "Dark sports dashboard for Virat Kohli Test stats with sample demo data.",
        "generic": f"Simple web app scaffold for: {request.app_name}.",
    }
    pages = {
        "calculator": ("home",),
        "cli_calculator": ("repl",),
        "todo": ("tasks",),
        "habit_tracker": ("habits",),
        "expense_tracker": ("ledger",),
        "landing_page": ("landing",),
        "kohli_stats": ("dashboard",),
        "generic": ("home",),
    }
    components = {
        "calculator": ("Calculator", "Keypad", "Display"),
        "cli_calculator": ("REPL", "Evaluator"),
        "todo": ("TodoList", "TodoItem", "FilterBar"),
        "habit_tracker": ("HabitGrid", "HabitCard", "StreakBadge"),
        "expense_tracker": ("TransactionForm", "TransactionList", "BalanceCard"),
        "landing_page": ("Hero", "Features", "HowItWorks", "CTA"),
        "kohli_stats": ("Hero", "StatCards", "StatsTable"),
        "generic": ("AppShell", "PlaceholderPanel"),
    }
    interactions = {
        "calculator": ("tap_digits", "operators", "equals", "clear", "keyboard"),
        "cli_calculator": ("repl_input", "evaluate_expression"),
        "todo": ("add_task", "toggle_complete", "delete_task", "filter"),
        "habit_tracker": ("add_habit", "mark_today", "view_streak"),
        "expense_tracker": ("add_transaction", "view_balance"),
        "landing_page": ("scroll", "cta_click"),
        "kohli_stats": ("view_stats", "scan_table"),
        "generic": ("view_placeholder",),
    }
    criteria = {
        "calculator": (
            "Digits and +, -, *, / work",
            "Divide-by-zero handled",
            "npm install and npm run build pass",
            "Local preview verified",
        ),
        "cli_calculator": (
            "Python syntax check passes",
            "Smoke test passes",
            "Run command documented",
        ),
        "todo": (
            "Add, complete, delete tasks",
            "Filter all/active/completed",
            "localStorage persistence",
            "npm run build passes",
        ),
        "habit_tracker": (
            "Add habits and mark today complete",
            "Streak and weekly grid visible",
            "localStorage persistence",
            "npm run build passes",
        ),
        "expense_tracker": (
            "Add income and expenses with category",
            "Balance and transaction list",
            "localStorage persistence",
            "npm run build passes",
        ),
        "landing_page": (
            "Hero, features, how it works, CTA",
            "Responsive layout",
            "npm run build passes",
        ),
        "kohli_stats": (
            "Headline, stat cards, and stats table",
            "Sample demo stats labeled clearly",
            "npm run build passes",
        ),
        "generic": (
            "Placeholder UI for requested idea",
            "Responsive layout",
            "npm run build passes",
        ),
    }
    return AppSpec(
        title=request.app_name,
        description=descriptions.get(request.app_type, descriptions["generic"]),
        stack=stack,
        pages=pages.get(request.app_type, ("home",)),
        components=components.get(request.app_type, components["generic"]),
        user_interactions=interactions.get(request.app_type, interactions["generic"]),
        acceptance_criteria=criteria.get(request.app_type, criteria["generic"]),
        template_id=template_id,
        app_type=request.app_type,
        app_name=request.app_name,
    )

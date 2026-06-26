"""App spec generation from parsed requests."""

from __future__ import annotations

from dataclasses import dataclass

from nova_core.orchestration.app_request import AppRequest

STACK = "Vite + React + TypeScript"


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
        "todo": "todo_react_vite",
        "habit_tracker": "habit_tracker_react_vite",
        "expense_tracker": "expense_tracker_react_vite",
        "landing_page": "landing_page_react_vite",
        "generic": "generic_react_vite",
    }
    return mapping.get(app_type, "generic_react_vite")


def build_app_spec(request: AppRequest) -> AppSpec:
    template_id = template_id_for_app_type(request.app_type)
    descriptions = {
        "calculator": "Responsive calculator with arithmetic, clear/delete, and keyboard support.",
        "todo": "Task list with add, complete, delete, filters, and localStorage persistence.",
        "habit_tracker": "Habit tracker with streaks, weekly grid, and localStorage persistence.",
        "expense_tracker": "Income/expense tracker with categories, balance, and localStorage.",
        "landing_page": f"Polished landing page for {request.app_name}.",
        "generic": f"Simple web app scaffold for: {request.app_name}.",
    }
    pages = {
        "calculator": ("home",),
        "todo": ("tasks",),
        "habit_tracker": ("habits",),
        "expense_tracker": ("ledger",),
        "landing_page": ("landing",),
        "generic": ("home",),
    }
    components = {
        "calculator": ("Calculator", "Keypad", "Display"),
        "todo": ("TodoList", "TodoItem", "FilterBar"),
        "habit_tracker": ("HabitGrid", "HabitCard", "StreakBadge"),
        "expense_tracker": ("TransactionForm", "TransactionList", "BalanceCard"),
        "landing_page": ("Hero", "Features", "HowItWorks", "CTA"),
        "generic": ("AppShell", "PlaceholderPanel"),
    }
    interactions = {
        "calculator": ("tap_digits", "operators", "equals", "clear", "keyboard"),
        "todo": ("add_task", "toggle_complete", "delete_task", "filter"),
        "habit_tracker": ("add_habit", "mark_today", "view_streak"),
        "expense_tracker": ("add_transaction", "view_balance"),
        "landing_page": ("scroll", "cta_click"),
        "generic": ("view_placeholder",),
    }
    criteria = {
        "calculator": (
            "Digits and +, -, *, / work",
            "Divide-by-zero handled",
            "npm install and npm run build pass",
            "Local preview verified",
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
        "generic": (
            "Placeholder UI for requested idea",
            "Responsive layout",
            "npm run build passes",
        ),
    }
    return AppSpec(
        title=request.app_name,
        description=descriptions.get(request.app_type, descriptions["generic"]),
        stack=STACK,
        pages=pages.get(request.app_type, ("home",)),
        components=components.get(request.app_type, components["generic"]),
        user_interactions=interactions.get(request.app_type, interactions["generic"]),
        acceptance_criteria=criteria.get(request.app_type, criteria["generic"]),
        template_id=template_id,
        app_type=request.app_type,
        app_name=request.app_name,
    )

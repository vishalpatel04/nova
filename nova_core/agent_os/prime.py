"""Prime — mission classification and squad selection."""

from __future__ import annotations

import re
from dataclasses import dataclass

CALCULATOR_PATTERNS = (
    re.compile(r"(?i)build a calculator app"),
    re.compile(r"(?i)create a calculator app"),
    re.compile(r"(?i)make a calculator app"),
    re.compile(r"(?i)build a calculator app and deploy"),
)

WEB_APP_PATTERNS = (
    re.compile(r"(?i)create a web app"),
    re.compile(r"(?i)build a web app"),
)


@dataclass(frozen=True)
class MissionClassification:
    mission_type: str
    commander: str
    squad: tuple[str, ...]
    risk_level: str
    acceptance_criteria: tuple[str, ...]


def classify_request(user_request: str) -> MissionClassification:
    text = user_request.strip()
    lowered = text.lower()

    if any(p.search(text) for p in CALCULATOR_PATTERNS):
        return MissionClassification(
            mission_type="engineering.app_build",
            commander="forge",
            squad=(
                "product_planner",
                "architect",
                "frontend_engineer",
                "qa_engineer",
                "fixer",
                "code_reviewer",
                "devops_deploy",
                "sentry",
            ),
            risk_level="medium",
            acceptance_criteria=(
                "Responsive calculator UI with +, -, *, /",
                "Divide-by-zero handled",
                "npm install and npm run build pass",
                "Local preview URL available",
                "External deploy blocked until approval",
            ),
        )

    if any(p.search(text) for p in WEB_APP_PATTERNS):
        return MissionClassification(
            mission_type="engineering.web_app",
            commander="forge",
            squad=("product_planner", "architect", "frontend_engineer", "qa_engineer", "sentry"),
            risk_level="medium",
            acceptance_criteria=("Working web app in workspace", "Build passes"),
        )

    if "deploy" in lowered and "calculator" in lowered:
        return classify_request(
            "build a calculator app, test it, preview it, and prepare deployment"
        )

    return MissionClassification(
        mission_type="general.assistance",
        commander="prime",
        squad=("archive",),
        risk_level="low",
        acceptance_criteria=("Respond with evidence-backed summary",),
    )


def is_calculator_mission(user_request: str) -> bool:
    return classify_request(user_request).mission_type == "engineering.app_build"

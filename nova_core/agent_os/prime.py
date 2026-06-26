"""Prime — mission classification and squad selection."""

from __future__ import annotations

from dataclasses import dataclass

from nova_core.orchestration.app_request import is_app_build_intent, parse_app_request

FORGE_SQUAD = (
    "product_planner",
    "architect",
    "frontend_engineer",
    "qa_engineer",
    "fixer",
    "code_reviewer",
    "devops_deploy",
    "sentry",
)


@dataclass(frozen=True)
class MissionClassification:
    mission_type: str
    commander: str
    squad: tuple[str, ...]
    risk_level: str
    acceptance_criteria: tuple[str, ...]


def classify_request(user_request: str) -> MissionClassification:
    app_request = parse_app_request(user_request)
    if app_request is not None or is_app_build_intent(user_request):
        parsed = app_request or parse_app_request(f"build a simple web app for {user_request}")
        criteria: tuple[str, ...] = (
            "Working app generated in NOVA workspace",
            "npm install and npm run build pass",
            "Local preview verified when possible",
            "External deploy blocked until approval",
        )
        if parsed and parsed.app_type == "calculator":
            criteria = (
                "Responsive calculator UI with +, -, *, /",
                "Divide-by-zero handled",
                "npm install and npm run build pass",
                "Local preview URL verified",
                "External deploy blocked until approval",
            )
        return MissionClassification(
            mission_type="engineering.app_build",
            commander="forge",
            squad=FORGE_SQUAD,
            risk_level="medium",
            acceptance_criteria=criteria,
        )

    return MissionClassification(
        mission_type="general.assistance",
        commander="prime",
        squad=("archive",),
        risk_level="low",
        acceptance_criteria=("Respond with evidence-backed summary",),
    )


def is_app_build_mission(user_request: str) -> bool:
    return is_app_build_intent(user_request)

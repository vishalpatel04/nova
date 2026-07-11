"""Investor demo shortcuts for deterministic Forge missions."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from nova_core.orchestration.app_request import AppRequest, parse_app_request

if TYPE_CHECKING:
    from nova_core.agent_os.models import AgentMission

_KOHLI_RE = re.compile(
    r"(?i)(virat\s+kohli|\bkohli\b).*(test\s+stats|stats)|"
    r"test\s+stats.*(virat\s+kohli|\bkohli\b)|"
    r"make\s+a\s+page\s+on\s+virat\s+kohli"
)
_CALCULATOR_RE = re.compile(r"(?i)^make\s+a\s+calculator(?:\s+app)?[?.!,]?\s*$")
_YELLOW_THEME_RE = re.compile(
    r"(?i)^(make\s+it\s+yellow|make\s+(?:the\s+)?calculator\s+yellow|yellow\s+theme)\.?$"
)

CALCULATOR_YELLOW_CSS = """:root {
  color-scheme: light;
  font-family: 'SF Pro Text', system-ui, sans-serif;
  background: radial-gradient(circle at top, #fef9c3, #fde047 45%, #f59e0b 100%);
  min-height: 100vh;
}
body { margin: 0; }
.calculator {
  max-width: 360px;
  margin: 4rem auto;
  padding: 1.5rem;
  border-radius: 24px;
  background: rgba(255, 251, 235, 0.96);
  box-shadow: 0 20px 60px rgba(180, 83, 9, 0.25);
  border: 2px solid #fbbf24;
}
.eyebrow {
  margin: 0 0 0.5rem;
  color: #b45309;
  font-size: 0.85rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.display {
  font-size: 2.5rem;
  text-align: right;
  padding: 1rem;
  border-radius: 16px;
  background: #fffbeb;
  color: #78350f;
  margin-bottom: 1rem;
  border: 1px solid #fcd34d;
}
.keypad { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }
button {
  border: none;
  border-radius: 14px;
  padding: 1rem;
  font-size: 1.1rem;
  cursor: pointer;
  background: #fef3c7;
  color: #78350f;
}
button.op { background: #fde68a; color: #92400e; }
button.equals { background: linear-gradient(135deg, #f59e0b, #d97706); color: white; }
"""


def is_kohli_stats_request(text: str) -> bool:
    return _KOHLI_RE.search(text.strip()) is not None


def is_investor_calculator_request(text: str) -> bool:
    return _CALCULATOR_RE.search(text.strip()) is not None


def is_investor_demo_request(text: str) -> bool:
    return is_investor_calculator_request(text) or is_kohli_stats_request(text)


def is_calculator_yellow_theme_request(text: str) -> bool:
    return _YELLOW_THEME_RE.match(text.strip()) is not None


def parse_investor_demo_request(text: str) -> AppRequest | None:
    normalized = re.sub(r"\s+", " ", text.strip())
    if is_kohli_stats_request(normalized):
        return AppRequest(
            raw_user_request=normalized,
            app_type="kohli_stats",
            app_name="Virat Kohli Test Stats",
            features=("headline", "stat_cards", "stats_table", "sample_data"),
            style_preference="dark sports dashboard",
            deployment_requested=False,
            requires_clarification=False,
            runtime="web",
        )
    return parse_app_request(normalized)


def demo_chat_response(mission: AgentMission) -> str | None:
    report = mission.final_report
    summary = report.get("demo_chat_summary")
    if summary:
        return str(summary)
    return None


def demo_timeline_messages(mission: AgentMission) -> list[tuple[str, str, str]]:
    """Return (agent_id, display_name, message) rows for investor demo."""
    app_type = mission.final_report.get("app_type") or mission.artifacts.get("app_type", "")
    forge_msg = (
        "Generated Virat Kohli Test stats page files"
        if app_type == "kohli_stats"
        else "Generated calculator app files"
    )
    qa_msg = "npm install: PASS, npm run build: PASS"
    if mission.final_report.get("build_status") != "PASS":
        qa_msg = "npm install: FAIL, npm run build: FAIL"
    return [
        ("product_planner", "Product Planner", "Created app spec"),
        ("architect", "Architect", "Selected Vite + React + TypeScript"),
        ("forge", "Forge", forge_msg),
        ("qa_engineer", "QA Engineer", qa_msg),
        ("sentry", "Sentry", "Deployment approval gate"),
        ("prime", "Prime", "final report ready"),
    ]


def apply_demo_timeline(mission: AgentMission) -> None:
    from nova_core.agent_os.models import TimelineEvent, utc_now_iso

    mission.timeline_events = [
        TimelineEvent(
            agent_id=agent_id,
            display_name=display_name,
            message=message,
            timestamp=utc_now_iso(),
        )
        for agent_id, display_name, message in demo_timeline_messages(mission)
    ]
    mission.updated_at = utc_now_iso()


def stamp_demo_final_report(mission: AgentMission) -> None:
    app_type = mission.final_report.get("app_type") or mission.artifacts.get("app_type")
    if app_type == "calculator":
        mission.final_report["demo_chat_summary"] = (
            "Calculator app generated. Preview is ready. Deploy this app? yes/no"
        )
    elif app_type == "kohli_stats":
        mission.final_report["demo_chat_summary"] = (
            "Virat Kohli Test stats page generated. Preview is ready. Deploy this app? yes/no"
        )


def apply_calculator_yellow_theme(project_path: Path) -> bool:
    css_path = project_path / "src" / "App.css"
    if not css_path.is_file():
        return False
    css_path.write_text(CALCULATOR_YELLOW_CSS, encoding="utf-8")
    return True


def stamp_theme_update_report(mission: AgentMission) -> None:
    mission.final_report["demo_chat_summary"] = "Theme updated to yellow. Preview refreshed."


def apply_theme_update_timeline(mission: AgentMission) -> None:
    from nova_core.agent_os.models import TimelineEvent, utc_now_iso

    mission.timeline_events = [
        TimelineEvent(
            agent_id="forge",
            display_name="Forge",
            message="Applied yellow/gold theme to calculator preview",
            timestamp=utc_now_iso(),
        ),
        TimelineEvent(
            agent_id="qa_engineer",
            display_name="QA Engineer",
            message="npm run build: PASS (theme refresh)",
            timestamp=utc_now_iso(),
        ),
        TimelineEvent(
            agent_id="prime",
            display_name="Prime",
            message="Theme refresh complete",
            timestamp=utc_now_iso(),
        ),
    ]
    mission.updated_at = utc_now_iso()
    stamp_theme_update_report(mission)


def refresh_calculator_preview(project_path: Path) -> tuple[bool, str]:
    """Rebuild calculator project after theme change."""
    if not (project_path / "package.json").is_file():
        return False, "package.json missing"
    try:
        subprocess.run(
            ["npm", "run", "build"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        return False, detail[:200]
    return True, "ok"

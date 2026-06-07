"""Schedule parsing and next-run computation for background tasks."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

_INTERVAL_RE = re.compile(r"^(\d+)(s|m|h|d)$", re.IGNORECASE)
_CRON_FIELD_RE = re.compile(r"^[\d*,/-]+$")
_DAILY_CRON_RE = re.compile(r"^(\d{1,2}|\*)\s+(\d{1,2}|\*)\s+\*\s+\*\s+\*$")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def validate_schedule_kind(kind: str) -> None:
    if kind not in {"once", "interval", "cron"}:
        raise ValueError(f"Unsupported schedule_kind: {kind}")


def validate_schedule_expression(kind: str, expression: str) -> None:
    validate_schedule_kind(kind)
    expr = expression.strip()
    if not expr:
        raise ValueError("schedule_expression is required")
    if kind == "interval":
        if not _INTERVAL_RE.match(expr):
            raise ValueError("interval must look like 30m, 6h, or 1d")
        return
    if kind == "once":
        try:
            datetime.fromisoformat(expr.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("once schedule must be ISO8601 datetime") from exc
        return
    if kind == "cron":
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError("cron must have exactly 5 fields")
        for part in parts:
            if not _CRON_FIELD_RE.match(part):
                raise ValueError("invalid cron field characters")
        if not _DAILY_CRON_RE.match(expr):
            raise ValueError("only daily cron supported: M H * * *")
        minute, hour = int(parts[0]), int(parts[1])
        if not (0 <= minute <= 59 and 0 <= hour <= 23):
            raise ValueError("cron minute/hour out of range")


def parse_interval(expression: str) -> timedelta:
    match = _INTERVAL_RE.match(expression.strip())
    if not match:
        raise ValueError("invalid interval expression")
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if amount <= 0:
        raise ValueError("interval must be positive")
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)


def compute_next_run(
    *,
    schedule_kind: str,
    schedule_expression: str,
    after: datetime | None = None,
) -> datetime:
    validate_schedule_expression(schedule_kind, schedule_expression)
    base = _as_utc(after or datetime.now(UTC))
    if schedule_kind == "once":
        run_at = _as_utc(datetime.fromisoformat(schedule_expression.strip().replace("Z", "+00:00")))
        return run_at
    if schedule_kind == "interval":
        return base + parse_interval(schedule_expression)
    parts = schedule_expression.split()
    minute, hour = int(parts[0]), int(parts[1])
    candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= base:
        candidate += timedelta(days=1)
    return candidate


def daily_cron_at(hour: int, minute: int = 0) -> str:
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("hour/minute out of range")
    return f"{minute} {hour} * * *"

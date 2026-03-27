# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Cron expression utilities for scheduled task execution."""

from datetime import UTC, datetime

from croniter import croniter


def validate_cron(expr: str) -> bool:
    """Return True if *expr* is a valid cron expression."""
    return croniter.is_valid(expr)


def next_occurrence(expr: str, after: datetime | None = None) -> datetime:
    """Compute the next occurrence of *expr* after the given time (UTC)."""
    base = after or datetime.now(UTC)
    cron = croniter(expr, base)
    return cron.get_next(datetime).replace(tzinfo=UTC)


def human_readable(expr: str) -> str:
    """Return a simple human-readable description of a cron expression."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return expr

    minute, hour, dom, month, dow = parts

    if minute == "0" and hour == "*":
        return "Every hour"
    if minute == "0" and dom == "*" and month == "*" and dow == "*":
        return f"Every day at {hour}:00 UTC"
    if dom == "*" and month == "*" and dow == "*":
        return f"Every day at {hour}:{minute.zfill(2)} UTC"

    return expr

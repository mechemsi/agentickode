# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Queue schedule utility — checks if current time is within allowed dispatch window."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("autodev.schedule")


def _parse_time(value: str) -> time:
    """Parse 'HH:MM' string to time object."""
    parts = value.split(":")
    return time(int(parts[0]), int(parts[1]))


def is_within_schedule(schedule: dict | None, utc_now: datetime | None = None) -> bool:
    """Return True if runs are allowed to dispatch right now.

    Fail-open: returns True (allow) on any error or missing config.

    Schedule schema::

        {
            "enabled": true,
            "timezone": "Europe/Vilnius",
            "days": {
                "0": {"start": "20:00", "end": "08:00"},  # Mon overnight
                "5": {"start": "00:00", "end": "23:59"},  # Sat all day
                "6": null                                   # Sun disabled
            }
        }

    Keys "0"-"6" = Python weekday() (0=Mon, 6=Sun).
    null value or missing key = day disabled (no runs).
    start > end = overnight window wrapping past midnight.
    """
    if not schedule or not isinstance(schedule, dict):
        return True

    if not schedule.get("enabled", False):
        return True

    try:
        tz_name = schedule.get("timezone", "UTC")
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        logger.warning(
            "Invalid timezone %r in queue schedule, allowing dispatch", schedule.get("timezone")
        )
        return True

    if utc_now is None:
        utc_now = datetime.now(UTC)

    local_now = utc_now.astimezone(tz)
    day_key = str(local_now.weekday())

    days = schedule.get("days")
    if days is None or not isinstance(days, dict):
        return True  # missing or malformed → fail-open

    if day_key not in days:
        return False  # day not configured = disabled

    day_config = days[day_key]
    if day_config is None:
        return False  # explicitly disabled

    if not isinstance(day_config, dict):
        return True  # malformed → fail-open

    try:
        start = _parse_time(day_config["start"])
        end = _parse_time(day_config["end"])
    except (KeyError, ValueError, TypeError):
        logger.warning("Malformed time in schedule for day %s, allowing dispatch", day_key)
        return True

    current_time = local_now.time()

    if start <= end:
        # Normal window: e.g. 09:00-17:00
        return start <= current_time < end
    else:
        # Overnight window: e.g. 20:00-08:00 (wraps past midnight)
        return current_time >= start or current_time < end
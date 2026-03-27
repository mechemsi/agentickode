# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Severity comparison for monitoring events."""

SEVERITY_ORDER = {
    "debug": 0,
    "info": 1,
    "warning": 2,
    "error": 3,
    "critical": 4,
    "fatal": 5,
}


def meets_threshold(event_severity: str, min_severity: str) -> bool:
    """Return True if *event_severity* is >= *min_severity*."""
    event_level = SEVERITY_ORDER.get(event_severity.lower(), 0)
    min_level = SEVERITY_ORDER.get(min_severity.lower(), 0)
    return event_level >= min_level

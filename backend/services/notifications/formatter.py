# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Format notification messages from raw event data."""

from backend.config import settings


def _run_link(run_id: int | str) -> str:
    """Build a deep link to a run detail page."""
    return f"{settings.app_base_url}/runs/{run_id}"


def _duration_str(seconds: float | int | None) -> str:
    """Convert seconds to a human-readable duration string."""
    if seconds is None:
        return ""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes = total // 60
    secs = total % 60
    if minutes < 60:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def _cost_str(cost: float | None) -> str:
    """Format a USD cost value."""
    if cost is None:
        return ""
    if cost < 0.01:
        return "<$0.01"
    return f"${cost:.2f}"


def format_notification(event_type: str, data: dict) -> str:
    """Convert a broadcaster event into a human-readable notification message."""
    run_id = data.get("run_id", "?")
    title = data.get("title", "")
    project = data.get("project_id", "")
    label = f"{project} #{run_id}"
    if title:
        label += f" \u2014 {title}"

    link = _run_link(run_id)

    if event_type == "run_started":
        return f"\U0001f680 Run Started: {label}\n\U0001f517 {link}"

    if event_type == "run_completed":
        duration = data.get("duration") or _duration_str(data.get("duration_seconds"))
        pr_url = data.get("pr_url", "")
        cost = _cost_str(data.get("total_cost_usd"))
        msg = f"\u2705 Run Completed: {label}"
        if duration:
            msg += f"\n\u23f1\ufe0f Duration: {duration}"
        if pr_url:
            msg += f"\n\U0001f517 PR: {pr_url}"
        if cost:
            msg += f"\n\U0001f4b0 Cost: {cost}"
        msg += f"\n\U0001f517 {link}"
        return msg

    if event_type == "run_failed":
        error = data.get("error", "Unknown error")
        return f"\u274c Run Failed: {label}\n\u26a0\ufe0f {error}\n\U0001f517 {link}"

    if event_type == "approval_requested":
        pr_url = data.get("pr_url", "")
        msg = f"\u23f3 Approval Requested: {label}"
        if pr_url:
            msg += f"\n\U0001f517 PR: {pr_url}"
        msg += f"\n\U0001f517 Review: {link}"
        return msg

    if event_type == "plan_review_requested":
        subtask_count = data.get("subtask_count", 0)
        msg = f"\U0001f4cb Plan Review Requested: {label}"
        if subtask_count:
            msg += f"\n\U0001f4dd {subtask_count} subtasks to review"
        msg += f"\n\U0001f517 Review: {link}"
        return msg

    if event_type == "cost_threshold_exceeded":
        cost = _cost_str(data.get("total_cost_usd"))
        threshold = _cost_str(data.get("threshold_usd"))
        msg = f"\U0001f4b8 Cost Threshold Exceeded: {label}"
        if cost:
            msg += f"\n\U0001f4b0 Current cost: {cost}"
        if threshold:
            msg += f"\n\U0001f6a8 Threshold: {threshold}"
        msg += f"\n\U0001f517 {link}"
        return msg

    return f"\U0001f514 {event_type}: {label}\n\U0001f517 {link}"
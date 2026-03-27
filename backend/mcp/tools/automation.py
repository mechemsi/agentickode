# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""MCP tools for managing automation rules."""

from fastmcp import Context

from backend.mcp.tools.projects import _api


async def list_automation_rules(ctx: Context, project_id: str) -> dict:
    """List automation rules for a project (includes global rules).

    Args:
        project_id: The project identifier.

    Returns:
        List of automation rules with event filters and action configs.
    """
    return await _api(ctx, "get", f"/projects/{project_id}/automation-rules")


async def create_automation_rule(
    ctx: Context,
    project_id: str,
    name: str,
    event_source: str,
    event_filter: dict,
    action_type: str,
    action_config: dict,
    cooldown_seconds: int = 300,
) -> dict:
    """Create an automation rule: "when X happens, do Y".

    Args:
        project_id: The project this rule applies to.
        name: Human-readable rule name.
        event_source: Event source type (run_event, webhook, monitoring).
        event_filter: Conditions to match (e.g. {"event_type": "run_failed"}).
        action_type: Action to take (create_run, notify, send_message).
        action_config: Action parameters (e.g. {"title": "Fix: ...", "description": "..."}).
        cooldown_seconds: Minimum seconds between triggers (default 300).

    Returns:
        Created automation rule details.
    """
    return await _api(
        ctx,
        "post",
        f"/projects/{project_id}/automation-rules",
        json={
            "name": name,
            "event_source": event_source,
            "event_filter": event_filter,
            "action_type": action_type,
            "action_config": action_config,
            "cooldown_seconds": cooldown_seconds,
        },
    )


async def update_automation_rule(
    ctx: Context,
    rule_id: int,
    enabled: bool | None = None,
    cooldown_seconds: int | None = None,
) -> dict:
    """Update an automation rule (enable/disable, change cooldown).

    Args:
        rule_id: The automation rule ID.
        enabled: Enable or disable the rule (optional).
        cooldown_seconds: New cooldown in seconds (optional).

    Returns:
        Updated automation rule details.
    """
    body = {}
    if enabled is not None:
        body["enabled"] = enabled
    if cooldown_seconds is not None:
        body["cooldown_seconds"] = cooldown_seconds
    return await _api(ctx, "put", f"/automation-rules/{rule_id}", json=body)

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""MCP tools for managing scheduled tasks."""

from fastmcp import Context

from backend.mcp.tools.projects import _api


async def list_scheduled_tasks(ctx: Context, project_id: str) -> dict:
    """List all scheduled tasks for a project.

    Args:
        project_id: The project identifier.

    Returns:
        List of scheduled tasks with cron expressions and status.
    """
    return await _api(ctx, "get", f"/projects/{project_id}/scheduled-tasks")


async def create_scheduled_task(
    ctx: Context,
    project_id: str,
    name: str,
    schedule: str,
    task_description: str,
    enabled: bool = True,
) -> dict:
    """Create a new scheduled task that runs on a cron schedule.

    Args:
        project_id: The project to schedule tasks for.
        name: Human-readable name (e.g. "Nightly dependency check").
        schedule: Cron expression (e.g. "0 3 * * *" for 3 AM daily).
        task_description: Description of the task for the AI agent.
        enabled: Whether the schedule is active.

    Returns:
        Created scheduled task details.
    """
    return await _api(
        ctx,
        "post",
        f"/projects/{project_id}/scheduled-tasks",
        json={
            "name": name,
            "schedule": schedule,
            "task_description": task_description,
            "enabled": enabled,
        },
    )


async def update_scheduled_task(
    ctx: Context,
    task_id: int,
    name: str | None = None,
    schedule: str | None = None,
    task_description: str | None = None,
    enabled: bool | None = None,
) -> dict:
    """Update an existing scheduled task.

    Args:
        task_id: The scheduled task ID.
        name: New name (optional).
        schedule: New cron expression (optional).
        task_description: New description (optional).
        enabled: Enable or disable (optional).

    Returns:
        Updated scheduled task details.
    """
    body = {}
    if name is not None:
        body["name"] = name
    if schedule is not None:
        body["schedule"] = schedule
    if task_description is not None:
        body["task_description"] = task_description
    if enabled is not None:
        body["enabled"] = enabled
    return await _api(ctx, "put", f"/scheduled-tasks/{task_id}", json=body)


async def trigger_scheduled_task(ctx: Context, task_id: int) -> dict:
    """Manually trigger a scheduled task to run immediately.

    Args:
        task_id: The scheduled task ID to trigger.

    Returns:
        Status and created run ID.
    """
    return await _api(ctx, "post", f"/scheduled-tasks/{task_id}/trigger")

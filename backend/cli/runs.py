# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI commands for task run management."""

from __future__ import annotations

import json

import click

from backend.cli.http import get, post, stream_sse
from backend.cli.output import output


@click.group()
def runs():
    """Manage task runs."""


@runs.command("list")
@click.option("--project", default=None, help="Filter by project ID.")
@click.option("--status", default=None, help="Filter by status.")
@click.option("--limit", default=20, type=int, help="Max results.")
@click.pass_context
def runs_list(ctx, project, status, limit):
    """List task runs."""
    params: dict = {"limit": limit}
    if project:
        params["project_id"] = project
    if status:
        params["status"] = status
    data = get("/runs", **params)
    items = data.get("items", data) if isinstance(data, dict) else data
    output(
        items,
        columns=[
            ("id", "ID", 6),
            ("project_id", "PROJECT", 20),
            ("title", "TITLE", 40),
            ("status", "STATUS", 15),
        ],
        quiet_key="id",
    )


@runs.command("create")
@click.option("--project", required=True, help="Project ID.")
@click.option("--title", required=True, help="Task title.")
@click.option("--description", default="", help="Task description.")
@click.option("--mode", type=click.Choice(["structured", "autonomous", "hybrid"]), default=None)
@click.pass_context
def runs_create(ctx, project, title, description, mode):
    """Create a new task run."""
    body: dict = {
        "project_id": project,
        "title": title,
        "description": description,
    }
    if mode:
        body["execution_mode"] = mode
    data = post("/runs", body)
    output(
        data,
        fields=[
            ("id", "Run ID"),
            ("project_id", "Project"),
            ("title", "Title"),
            ("status", "Status"),
        ],
        quiet_key="id",
    )


@runs.command("get")
@click.argument("run_id", type=int)
@click.pass_context
def runs_get(ctx, run_id):
    """Get run details."""
    data = get(f"/runs/{run_id}")
    output(
        data,
        fields=[
            ("id", "Run ID"),
            ("project_id", "Project"),
            ("title", "Title"),
            ("status", "Status"),
            ("current_phase", "Phase"),
            ("pr_url", "PR URL"),
            ("created_at", "Created"),
        ],
    )


@runs.command("logs")
@click.argument("run_id", type=int)
@click.option("--tail", default=50, type=int, help="Number of log lines.")
@click.option("--follow", "-f", is_flag=True, help="Follow live output.")
@click.pass_context
def runs_logs(ctx, run_id, tail, follow):
    """Show run logs."""
    if follow:
        click.echo(f"Streaming logs for run #{run_id}... (Ctrl+C to stop)")
        for data_str in stream_sse(f"/runs/{run_id}/agent-stream"):
            try:
                event = json.loads(data_str)
                if event.get("type") == "progress":
                    click.echo(
                        f"  [turn {event.get('turns', '?')}] context: {event.get('context_pct', 0):.0f}%"
                    )
                elif event.get("type") == "done":
                    click.echo(f"  Done: {event.get('result', event.get('status', ''))[:200]}")
                    break
                elif event.get("error"):
                    click.echo(f"  Error: {event['error']}")
            except json.JSONDecodeError:
                click.echo(f"  {data_str}")
    else:
        data = get(f"/runs/{run_id}")
        logs = data.get("logs", [])
        for log in logs[-tail:]:
            phase = log.get("phase", "")
            msg = log.get("message", "")
            click.echo(f"  [{phase}] {msg}")


@runs.command("approve")
@click.argument("run_id", type=int)
@click.pass_context
def runs_approve(ctx, run_id):
    """Approve a run waiting for approval."""
    post(f"/runs/{run_id}/approve")
    click.echo(f"Run #{run_id} approved.")


@runs.command("reject")
@click.argument("run_id", type=int)
@click.option("--reason", default=None, help="Rejection reason.")
@click.pass_context
def runs_reject(ctx, run_id, reason):
    """Reject a run waiting for approval."""
    body = {"reason": reason} if reason else {}
    post(f"/runs/{run_id}/reject", body)
    click.echo(f"Run #{run_id} rejected.")


@runs.command("cancel")
@click.argument("run_id", type=int)
@click.pass_context
def runs_cancel(ctx, run_id):
    """Cancel a running or pending run."""
    post(f"/runs/{run_id}/cancel")
    click.echo(f"Run #{run_id} cancelled.")


@runs.command("retry")
@click.argument("run_id", type=int)
@click.pass_context
def runs_retry(ctx, run_id):
    """Retry a failed run."""
    post(f"/runs/{run_id}/retry")
    click.echo(f"Run #{run_id} retried.")

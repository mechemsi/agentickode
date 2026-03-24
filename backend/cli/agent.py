# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI commands for agent control — interact with running autonomous agents."""

from __future__ import annotations

import json

import click

from backend.cli.http import get, post
from backend.cli.output import output


@click.group()
def agent():
    """Control running agents."""


@agent.command("message")
@click.argument("run_id", type=int)
@click.argument("message")
@click.pass_context
def agent_message(ctx, run_id, message):
    """Send a message to a running agent."""
    post(f"/runs/{run_id}/agent/message", {"message": message})
    click.echo(f"Message sent to agent on run #{run_id}.")


@agent.command("pause")
@click.argument("run_id", type=int)
@click.pass_context
def agent_pause(ctx, run_id):
    """Pause a running agent."""
    post(f"/runs/{run_id}/agent/pause")
    click.echo(f"Agent on run #{run_id} paused.")


@agent.command("resume")
@click.argument("run_id", type=int)
@click.pass_context
def agent_resume(ctx, run_id):
    """Resume a paused agent."""
    post(f"/runs/{run_id}/agent/resume")
    click.echo(f"Agent on run #{run_id} resumed.")


@agent.command("episodes")
@click.argument("run_id", type=int)
@click.pass_context
def agent_episodes(ctx, run_id):
    """List episodes for an autonomous run."""
    data = get(f"/runs/{run_id}/episodes")
    output(
        data,
        columns=[
            ("episode_number", "EP", 4),
            ("status", "STATUS", 12),
            ("turn_count", "TURNS", 6),
            ("tokens_used", "TOKENS", 8),
            ("context_usage_pct", "CTX %", 6),
            ("git_checkpoint_sha", "COMMIT", 9),
        ],
        quiet_key="episode_number",
    )


@agent.command("query")
@click.argument("run_id", type=int)
@click.argument("question")
@click.option("--timeout", default=120, type=int, help="Max seconds to wait.")
@click.pass_context
def agent_query(ctx, run_id, question, timeout):
    """Ask a question to a run's agent and get a response."""
    data = post(f"/runs/{run_id}/agent/query", {"question": question, "timeout": timeout})
    output(
        data,
        fields=[("response", "Response"), ("session_id", "Session")],
        quiet_key="response",
    )


@agent.command("diff")
@click.argument("run_id", type=int)
@click.pass_context
def agent_diff(ctx, run_id):
    """Show git diff of changes made by the agent."""
    data = get(f"/runs/{run_id}/agent/diff")
    if isinstance(data, dict):
        click.echo(data.get("summary", ""))
        diff = data.get("diff", "")
        if diff:
            click.echo(f"\n{diff}")


@agent.command("plan")
@click.argument("run_id", type=int)
@click.pass_context
def agent_plan(ctx, run_id):
    """Show the agent's implementation plan."""
    data = get(f"/runs/{run_id}/agent/plan")
    plan = data.get("plan")
    if plan:
        if isinstance(plan, dict):
            click.echo(json.dumps(plan, indent=2))
        else:
            click.echo(plan)
    else:
        click.echo("No plan found.")

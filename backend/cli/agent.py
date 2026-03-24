# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI commands for agent control — interact with running autonomous agents."""

from __future__ import annotations

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

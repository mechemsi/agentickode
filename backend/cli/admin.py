# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI commands for platform administration."""

from __future__ import annotations

import click

from backend.cli.http import get
from backend.cli.output import output


@click.group()
def admin():
    """Platform administration."""


@admin.command("agents")
@click.pass_context
def admin_agents(ctx):
    """List all configured AI agents."""
    data = get("/agents")
    output(
        data,
        columns=[
            ("agent_name", "AGENT", 15),
            ("display_name", "NAME", 20),
            ("enabled", "ENABLED", 8),
            ("supports_session", "SESSIONS", 9),
        ],
        quiet_key="agent_name",
    )


@admin.command("analytics")
@click.option("--period", default="7d", help="Time period (7d, 30d, 90d).")
@click.pass_context
def admin_analytics(ctx, period):
    """Show platform analytics."""
    data = get("/analytics/summary", period=period)
    output(
        data,
        fields=[
            ("total_runs", "Total runs"),
            ("completed_runs", "Completed"),
            ("failed_runs", "Failed"),
            ("total_cost_usd", "Total cost ($)"),
            ("avg_duration_seconds", "Avg duration (s)"),
        ],
    )


@admin.command("health")
@click.pass_context
def admin_health(ctx):
    """Check platform health."""
    data = get("/health")
    output(
        data,
        fields=[
            ("status", "Status"),
            ("database", "Database"),
            ("worker", "Worker"),
            ("queue", "Queue"),
        ],
    )

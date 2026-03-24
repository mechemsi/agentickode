# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""AgenticKode CLI — control the platform from any terminal or AI agent."""

from __future__ import annotations

import click

from backend.cli.admin import admin
from backend.cli.agent import agent
from backend.cli.projects import projects
from backend.cli.runs import runs
from backend.cli.servers import servers
from backend.cli.workspace import workspace


@click.group()
@click.option(
    "--url",
    envvar="AGENTICKODE_URL",
    default="http://localhost:8000",
    help="Platform API URL.",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.option("--quiet", is_flag=True, help="Minimal output (IDs only).")
@click.pass_context
def cli(ctx: click.Context, url: str, json_output: bool, quiet: bool) -> None:
    """AgenticKode — AI coding automation platform CLI."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url.rstrip("/")
    ctx.obj["json"] = json_output
    ctx.obj["quiet"] = quiet


cli.add_command(projects)
cli.add_command(runs)
cli.add_command(agent)
cli.add_command(servers)
cli.add_command(workspace)
cli.add_command(admin)


def main() -> None:
    cli(auto_envvar_prefix="AGENTICKODE")


if __name__ == "__main__":
    main()

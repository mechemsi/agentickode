# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI commands for workspace server management."""

from __future__ import annotations

import click

from backend.cli.http import get, post
from backend.cli.output import output


@click.group()
def servers():
    """Manage workspace servers."""


@servers.command("list")
@click.pass_context
def servers_list(ctx):
    """List all workspace servers."""
    data = get("/workspace-servers")
    output(
        data,
        columns=[
            ("id", "ID", 4),
            ("hostname", "HOST", 25),
            ("ssh_user", "USER", 10),
            ("status", "STATUS", 12),
            ("setup_status", "SETUP", 12),
        ],
        quiet_key="id",
    )


@servers.command("add")
@click.option("--hostname", required=True, help="Server hostname or IP.")
@click.option("--ssh-user", default="root", help="SSH user.")
@click.option("--ssh-port", default=22, type=int, help="SSH port.")
@click.option("--ssh-key-id", default=None, type=int, help="SSH key pair ID.")
@click.pass_context
def servers_add(ctx, hostname, ssh_user, ssh_port, ssh_key_id):
    """Add a new workspace server."""
    body: dict = {
        "hostname": hostname,
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
    }
    if ssh_key_id:
        body["ssh_key_id"] = ssh_key_id
    data = post("/workspace-servers", body)
    output(
        data,
        fields=[("id", "Server ID"), ("hostname", "Host"), ("status", "Status")],
        quiet_key="id",
    )


@servers.command("setup")
@click.argument("server_id", type=int)
@click.pass_context
def servers_setup(ctx, server_id):
    """Run setup on a workspace server."""
    click.echo(f"Starting setup for server #{server_id}...")
    data = post(f"/workspace-servers/{server_id}/setup")
    click.echo(f"Setup initiated. Status: {data.get('status', 'unknown')}")


@servers.command("status")
@click.argument("server_id", type=int)
@click.pass_context
def servers_status(ctx, server_id):
    """Get server status."""
    data = get(f"/workspace-servers/{server_id}")
    output(
        data,
        fields=[
            ("id", "Server ID"),
            ("hostname", "Host"),
            ("ssh_user", "SSH User"),
            ("status", "Status"),
            ("setup_status", "Setup"),
        ],
    )

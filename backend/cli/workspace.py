# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI commands for workspace operations — remote commands and session management."""

from __future__ import annotations

import click

from backend.cli.http import get, post
from backend.cli.output import output


@click.group()
def workspace():
    """Workspace operations — remote commands and sessions."""


# ─── Remote commands ────────────────────────────────────────────────


@workspace.command("run")
@click.argument("server_id", type=int)
@click.argument("command")
@click.option("--timeout", default=30, type=int)
@click.option("--user", default=None, help="Run as user.")
@click.pass_context
def ws_run(ctx, server_id, command, timeout, user):
    """Run a command on a workspace server via SSH."""
    body: dict = {"command": command, "timeout": timeout}
    if user:
        body["user"] = user
    data = post(f"/workspace-servers/{server_id}/exec", body)
    if isinstance(data, dict):
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        rc = data.get("exit_code", -1)
        if stdout:
            click.echo(stdout)
        if stderr:
            click.echo(stderr, err=True)
        if rc != 0:
            click.echo(f"Exit code: {rc}", err=True)


@workspace.command("read")
@click.argument("server_id", type=int)
@click.argument("file_path")
@click.pass_context
def ws_read(ctx, server_id, file_path):
    """Read a file from a workspace server."""
    data = get(f"/workspace-servers/{server_id}/read-file?path={file_path}")
    if isinstance(data, dict):
        click.echo(data.get("content", ""))


@workspace.command("ls")
@click.argument("server_id", type=int)
@click.argument("path", default="/")
@click.pass_context
def ws_ls(ctx, server_id, path):
    """List a directory on a workspace server."""
    data = get(f"/workspace-servers/{server_id}/ls?path={path}")
    if isinstance(data, dict):
        click.echo(data.get("listing", ""))


# ─── Session management ────────────────────────────────────────────


@workspace.group("sessions")
def sessions():
    """Manage workspace agent sessions."""


@sessions.command("list")
@click.option("--server", default=None, type=int, help="Filter by server ID.")
@click.option("--status", default=None, help="Filter by status.")
@click.pass_context
def sessions_list(ctx, server, status):
    """List workspace sessions."""
    params: dict = {}
    if server:
        params["server_id"] = server
    if status:
        params["status"] = status
    data = get("/sessions", **params)
    output(
        data,
        columns=[
            ("id", "ID", 5),
            ("agent_name", "AGENT", 10),
            ("display_name", "NAME", 20),
            ("status", "STATUS", 10),
            ("user_context", "USER", 8),
        ],
        quiet_key="id",
    )


@sessions.command("create")
@click.option("--server", required=True, type=int, help="Server ID.")
@click.option("--agent", default="claude", help="Agent name.")
@click.option("--project", default=None, help="Project ID.")
@click.option("--path", default=None, help="Workspace path.")
@click.option("--user", default="coder", help="User context.")
@click.option("--name", default=None, help="Display name.")
@click.pass_context
def sessions_create(ctx, server, agent, project, path, user, name):
    """Create a workspace agent session."""
    body: dict = {
        "workspace_server_id": server,
        "agent_name": agent,
        "user_context": user,
    }
    if project:
        body["project_id"] = project
    if path:
        body["workspace_path"] = path
    if name:
        body["display_name"] = name
    data = post("/sessions", body)
    output(
        data,
        fields=[("id", "Session ID"), ("session_id", "UUID"), ("status", "Status")],
        quiet_key="id",
    )


@sessions.command("send")
@click.argument("session_id", type=int)
@click.argument("message")
@click.pass_context
def sessions_send(ctx, session_id, message):
    """Send a message to a workspace session."""
    data = post(f"/sessions/{session_id}/send", {"message": message})
    if isinstance(data, dict):
        out = data.get("output", "")
        if out:
            click.echo(out)


@sessions.command("capture")
@click.argument("session_id", type=int)
@click.option("--lines", default=50, type=int)
@click.pass_context
def sessions_capture(ctx, session_id, lines):
    """Capture output from a workspace session."""
    data = get(f"/sessions/{session_id}/capture", lines=lines)
    if isinstance(data, dict):
        click.echo(data.get("output", ""))


@sessions.command("close")
@click.argument("session_id", type=int)
@click.pass_context
def sessions_close(ctx, session_id):
    """Close a workspace session."""
    from backend.cli.http import delete

    delete(f"/sessions/{session_id}")
    click.echo(f"Session #{session_id} closed.")

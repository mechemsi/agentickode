# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLI commands for project management."""

from __future__ import annotations

import json

import click

from backend.cli.http import delete, get, post, put
from backend.cli.output import output


@click.group()
def projects():
    """Manage projects."""


@projects.command("list")
@click.option("--status", type=click.Choice(["active", "archived"]), default=None)
@click.pass_context
def projects_list(ctx, status):
    """List all projects."""
    params = {}
    if status:
        params["status"] = status
    data = get("/projects", **params)
    output(
        data,
        columns=[
            ("project_id", "PROJECT", 25),
            ("repo_url", "REPO", 45),
            ("git_provider", "PROVIDER", 10),
        ],
        quiet_key="project_id",
    )


@projects.command("get")
@click.argument("project_id")
@click.pass_context
def projects_get(ctx, project_id):
    """Get project details."""
    data = get(f"/projects/{project_id}")
    output(
        data,
        fields=[
            ("project_id", "Project"),
            ("repo_url", "Repo URL"),
            ("git_provider", "Provider"),
            ("default_branch", "Branch"),
            ("execution_mode", "Mode"),
        ],
    )


@projects.command("create")
@click.option("--repo-url", required=True, help="Git repository URL.")
@click.option(
    "--provider", required=True, type=click.Choice(["github", "gitlab", "gitea", "bitbucket"])
)
@click.option("--name", default=None, help="Project name (auto-detected from URL if omitted).")
@click.option("--mode", type=click.Choice(["structured", "autonomous", "hybrid"]), default=None)
@click.pass_context
def projects_create(ctx, repo_url, provider, name, mode):
    """Create a new project."""
    body = {"repo_url": repo_url, "git_provider": provider}
    if name:
        body["project_id"] = name
    if mode:
        body["autonomy_config"] = {"execution_mode": mode}
    data = post("/projects", body)
    output(data, fields=[("project_id", "Project"), ("repo_url", "Repo")], quiet_key="project_id")


@projects.command("update")
@click.argument("project_id")
@click.option("--mode", type=click.Choice(["structured", "autonomous", "hybrid"]), default=None)
@click.option("--episode-config", default=None, help="Episode config JSON string.")
@click.pass_context
def projects_update(ctx, project_id, mode, episode_config):
    """Update project settings."""
    body: dict = {}
    if mode or episode_config:
        ac: dict = {}
        if mode:
            ac["execution_mode"] = mode
        if episode_config:
            ac["episode_config"] = json.loads(episode_config)
        body["autonomy_config"] = ac
    data = put(f"/projects/{project_id}", body)
    click.echo(f"Project {data.get('project_id', project_id)} updated.")


@projects.command("delete")
@click.argument("project_id")
@click.confirmation_option(prompt="Are you sure you want to delete this project?")
@click.pass_context
def projects_delete(ctx, project_id):
    """Delete a project."""
    delete(f"/projects/{project_id}")
    click.echo(f"Project {project_id} deleted.")

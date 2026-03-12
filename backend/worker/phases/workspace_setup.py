# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 0: Workspace setup — clone/scaffold/cluster.

Ported from activities.py setup_workspace (L162-316).
All operations execute on the remote workspace server via SSH.
"""

from __future__ import annotations

import logging
import shlex
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps, get_git_provider
from backend.services.git.ops import get_repo_https_url
from backend.services.http_client import get_http_client
from backend.services.workspace.sandbox import RemoteSandbox
from backend.services.workspace.ssh_service import SSHService
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._helpers import get_auth_url, get_project_token, get_workspace_server

logger = logging.getLogger("autodev.phases.workspace_setup")

PHASE_META = {
    "description": "Set up workspace on remote server",
}

LogFn = Callable[..., Awaitable[None]]


def _phase_log(run_id: int) -> LogFn:
    """Return a shorthand log function bound to a run + phase."""

    async def _log(msg: str, level: str = "info", metadata: dict | None = None) -> None:
        await broadcaster.log(run_id, msg, level=level, phase="workspace_setup", metadata=metadata)

    return _log


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> None:
    _log = _phase_log(task_run.id)

    project_token = await get_project_token(task_run, session)

    await _log(f"Connecting to workspace server for project {task_run.project_id}")
    server = await get_workspace_server(task_run, session)
    ssh = SSHService.for_server(server)
    await _log(f"Connected to {ssh.hostname}:{ssh.port} as {ssh.username}")

    remote_git = RemoteGitOps(ssh)
    remote_sandbox = RemoteSandbox(ssh)

    ws_cfg = task_run.workspace_config or {}
    ws_type = ws_cfg.get("workspace_type", "existing")

    # Resolve full workspace path: prepend workspace_root for relative paths
    raw_path = task_run.workspace_path
    if raw_path.startswith("/"):
        workspace = raw_path
    else:
        workspace_root = server.workspace_root or "/home/workspace"
        workspace = f"{workspace_root}/{raw_path}".rstrip("/")
    task_run.workspace_path = workspace

    repos_cloned: list[str] = []

    await _log(f"Workspace type={ws_type}, path={workspace}")

    if ws_type == "existing":
        branch = str(task_run.default_branch)
        await _log(f"Checking if repo exists at {workspace}")
        if await remote_git.has_repo(workspace):
            await _log(
                f"Repo found, resetting to origin/{branch}",
                metadata=make_log_metadata("ssh_command", command=f"git checkout {branch}"),
            )
            # Clean reset: discard local changes and switch to default branch
            await remote_git.run_git(["checkout", "-f", branch], cwd=workspace)
            await remote_git.run_git(["clean", "-fd"], cwd=workspace)
            await remote_git.run_git(["pull", "origin", branch], cwd=workspace)
            await _log("Reset and pull complete")
        else:
            await _log("No repo found, will clone fresh")
            await remote_git.mkdir(workspace)
            repo_url, branch = _resolve_single_repo(task_run, ws_cfg)
            auth_url, method = await get_auth_url(
                repo_url, task_run.git_provider, ssh, token_override=project_token
            )
            await _log(
                f"Cloning {repo_url} (branch={branch}, auth={method})",
                metadata=make_log_metadata(
                    "ssh_command", command=f"git clone {repo_url}", branch=branch
                ),
            )
            await remote_git.clone(auth_url, workspace, branch=branch)
            await _log("Clone complete")
        repos_cloned.append(workspace)

    elif ws_type == "new":
        await _log("Scaffolding new project")
        await remote_git.mkdir(workspace)
        await _scaffold_new(task_run, workspace, ws_cfg, remote_git, ssh, _log, project_token)
        repos_cloned.append(workspace)

    elif ws_type == "cluster":
        await remote_git.mkdir(workspace)
        repos = ws_cfg.get("repos", [])
        if not repos:
            raise ValueError("workspace_type=cluster requires at least one repo")
        for i, repo in enumerate(repos):
            repo_url = repo["url"]
            repo_branch = repo.get("branch", task_run.default_branch)
            dir_name = repo.get("path") or repo_url.rstrip("/").split("/")[-1].replace(".git", "")
            dest = f"{workspace}/{dir_name}"
            auth_url, method = await get_auth_url(
                repo_url, task_run.git_provider, ssh, token_override=project_token
            )
            await _log(f"Repo {i + 1}/{len(repos)}: {repo_url} -> {dir_name} (auth={method})")
            await remote_git.clone_or_pull(auth_url, dest, branch=repo_branch)
            repos_cloned.append(repo_url)

        sb = ws_cfg.get("sandbox")
        if sb:
            await _log(f"Starting sandbox (template={sb['template']})")
            started, url = await remote_sandbox.start_sandbox(
                workspace,
                template=sb["template"],
                task_id=task_run.task_id,
                mount_points=sb.get("mount_points"),
                env_vars=sb.get("env_vars"),
                http_port=sb.get("http_port", 8080),
            )
            if started:
                await _log(f"Sandbox started at {url}")
            else:
                await _log("Sandbox failed to start", level="warning")
    else:
        raise ValueError(f"Unknown workspace_type: {ws_type}")

    # Ensure worker user can access the workspace (clone runs as root)
    worker_user = server.worker_user
    if worker_user and ssh.username == "root":
        ws_quoted = shlex.quote(workspace)
        await _log(f"Setting workspace ownership to {worker_user}")
        await ssh.run_command(f"chown -R {worker_user}:{worker_user} {ws_quoted}", timeout=60)

    task_run.workspace_result = {"workspace_path": workspace, "repos_cloned": repos_cloned}
    await session.commit()
    await _log(f"Workspace ready: {len(repos_cloned)} repo(s)")


def _resolve_single_repo(task_run: TaskRun, ws_cfg: dict) -> tuple[str, str]:
    repos = ws_cfg.get("repos", [])
    if repos:
        r = repos[0]
        return r["url"], r.get("branch", task_run.default_branch)
    if task_run.repo_owner and task_run.repo_name:
        url = get_repo_https_url(task_run.git_provider, task_run.repo_owner, task_run.repo_name)
        return url, str(task_run.default_branch)
    raise ValueError("workspace_type=existing requires repos list or repo_owner+repo_name")


async def _scaffold_new(
    task_run: TaskRun,
    workspace: str,
    ws_cfg: dict,
    remote_git: RemoteGitOps,
    ssh: SSHService,
    _log: LogFn,
    project_token: str | None = None,
) -> None:
    await _log("Initializing git repository")
    await remote_git.run_git(["init"], cwd=workspace)
    await remote_git.run_git(["checkout", "-b", task_run.default_branch], cwd=workspace)

    scaffold_template = ws_cfg.get("scaffold_template")
    if scaffold_template:
        await _log(f"Running scaffold template: {scaffold_template}")
        script = f"/opt/autodev/docker/sandboxes/{scaffold_template}/scaffold.sh"
        cmd = f"test -f {shlex.quote(script)} && bash {shlex.quote(script)}"
        await ssh.run_command(f"cd {shlex.quote(workspace)} && {cmd}", timeout=300)

    await _log("Creating initial commit")
    await remote_git.run_git(["add", "-A"], cwd=workspace)
    await remote_git.run_git(
        ["commit", "-m", "Initial project scaffold", "--allow-empty"], cwd=workspace
    )

    if task_run.repo_owner and task_run.repo_name:
        await _log(f"Creating remote repo: {task_run.repo_owner}/{task_run.repo_name}")
        provider = get_git_provider(
            task_run.git_provider, get_http_client(), access_token=project_token
        )
        ok = await provider.create_repo(task_run.repo_owner, task_run.repo_name)

        base_url = get_repo_https_url(
            task_run.git_provider, task_run.repo_owner, task_run.repo_name
        )

        if ok:
            remote_url, _ = await get_auth_url(
                base_url, task_run.git_provider, ssh, token_override=project_token
            )
            await remote_git.run_git(["remote", "add", "origin", remote_url], cwd=workspace)
            await _log(f"Pushing to origin/{task_run.default_branch}")
            await remote_git.run_git(
                ["push", "-u", "origin", task_run.default_branch], cwd=workspace
            )
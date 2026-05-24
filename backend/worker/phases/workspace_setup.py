# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 0: Workspace setup — clone/scaffold/cluster.

Ported from activities.py setup_workspace (L162-316).
All operations execute on the remote workspace server via SSH.
"""

from __future__ import annotations

import contextlib
import logging
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.repositories.readiness_repo import WorkspaceReadinessRepository
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps, get_git_provider
from backend.services.git.ops import get_repo_https_url
from backend.services.http_client import get_http_client
from backend.services.workspace.command_executor import CommandExecutor, executor_for_server
from backend.services.workspace.local_path import LocalPathError, validate_local_path
from backend.services.workspace.readiness_service import (
    TTL_DAYS,
    WorkspaceReadinessService,
    format_fix_guide,
)
from backend.services.workspace.sandbox import RemoteSandbox
from backend.services.workspace.usernames import validate_username
from backend.services.workspace.worktree import WorktreeManager, make_worktree_paths
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._helpers import (
    get_auth_url,
    get_project_config,
    get_project_token,
    get_workspace_server,
)

logger = logging.getLogger("agentickode.phases.workspace_setup")

PHASE_META = {
    "kind": "builtin",
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
    ssh = executor_for_server(server)
    await _log(f"Connected to {ssh.hostname}:{ssh.port} as {ssh.username}")

    remote_git = RemoteGitOps(ssh)
    remote_sandbox = RemoteSandbox(ssh)

    project = await get_project_config(task_run, session)
    ws_cfg = task_run.workspace_config or {}
    ws_type = ws_cfg.get("workspace_type", "existing")

    # Effective worker user: project override > server default. Used for
    # ``chown`` decisions and the safe.directory git config. Step-level
    # ``params.run_as`` is applied later in step runners, not here.
    worker_user = (project.worker_user_override if project else None) or server.worker_user
    # Reject unsafe usernames before any of them flow into runuser/chown
    # strings below. Falsy values (None/"") are fine — they just mean
    # "no user drop".
    if worker_user:
        validate_username(worker_user, field="worker_user")

    # ``runuser``-style chown / safe.directory wrapping is needed both for
    # SSH-as-root (the historical case) and for local platform servers
    # (``server_type='local'``) where ``LocalCommandService.username`` is
    # the backend's own OS user and never equals ``"root"`` in SSH terms.
    # Skip when we're already running as the target user — ``runuser``
    # from a non-root caller typically fails without PAM/sudo config.
    is_local_server = getattr(server, "server_type", None) == "local"
    can_drop_privileges = ssh.username == "root"
    needs_user_drop = (
        bool(worker_user)
        and worker_user != ssh.username
        and (can_drop_privileges or is_local_server)
    )

    # --- Local-path shortcut: skip clone entirely ----------------------
    # When ``project.local_path`` is set we assume the operator has the
    # repo checked out on the workspace server. We validate (must exist,
    # be a git repo, working tree clean) and use it as the workspace
    # directly. ``ws_type``-specific branches are skipped — there's
    # nothing to clone or scaffold.
    local_path = project.local_path if project else None
    if local_path:
        await _log(f"Using project.local_path={local_path}, skipping clone")
        try:
            status = await validate_local_path(ssh, local_path)
        except LocalPathError as exc:
            await _log(str(exc), level="error")
            raise
        workspace = status.path
        task_run.workspace_path = workspace
        repos_cloned: list[str] = [workspace]
        # We deliberately skip the workspace-wide chown below: chown'ing
        # the user's working copy would change ownership of their files.
        # The per-worktree chown still runs when strategy=worktree, which
        # only touches ``.worktrees/run-X-Y``.
    else:
        # Resolve full workspace path: prepend workspace_root for relative paths.
        raw_path = task_run.workspace_path
        if raw_path.startswith("/"):
            workspace = raw_path
        else:
            workspace_root = server.workspace_root or "/home/workspace"
            workspace = f"{workspace_root}/{raw_path}".rstrip("/")
        task_run.workspace_path = workspace
        repos_cloned = []

    await _log(f"Workspace type={ws_type}, path={workspace}")

    # Mark workspace safe for git to avoid "dubious ownership" errors
    # when repo is cloned as root but operated by worker user
    await remote_git._mark_safe_directory(workspace)
    if needs_user_drop:
        safe_cmd = (
            f"runuser -l {shlex.quote(worker_user)} -c "
            f"'git config --global --add safe.directory {shlex.quote(workspace)}'"
        )
        with contextlib.suppress(Exception):
            await ssh.run_command(safe_cmd, timeout=10)

    if local_path:
        # Nothing to clone or scaffold — the operator's checkout *is* the
        # workspace. We still run the worktree branch below so concurrent
        # runs stay isolated under ``<local_path>/.worktrees/``.
        pass
    elif ws_type == "existing":
        branch = str(task_run.default_branch)

        # Ensure clone exists and is up-to-date
        if await remote_git.has_repo(workspace):
            await _log(f"Repo found at {workspace}, pulling latest")
            await remote_git.run_git(["fetch", "origin"], cwd=workspace)
            await remote_git.run_git(["checkout", "-f", branch], cwd=workspace)
            await remote_git.run_git(["reset", "--hard", f"origin/{branch}"], cwd=workspace)
            await remote_git.run_git(["clean", "-fd"], cwd=workspace)
        else:
            await _log(f"No repo found, cloning to {workspace}")
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

        # Clean up any stale .autodev from previous runs
        await ssh.run_command(f"rm -rf {shlex.quote(workspace)}/.autodev", timeout=10)
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

    # Ensure worker user can access workspace (clone runs as root). Skip
    # when ``local_path`` is in use — that's the operator's working copy
    # and we must not rewrite ownership of their files.
    if needs_user_drop and not local_path:
        await _log(f"Setting workspace ownership to {worker_user}")
        owned_quoted = shlex.quote(workspace)
        user_quoted = shlex.quote(worker_user)
        await ssh.run_command(f"chown -R {user_quoted}:{user_quoted} {owned_quoted}", timeout=60)

    workspace_result: dict = {"workspace_path": workspace, "repos_cloned": repos_cloned}

    # Optional worktree-per-run strategy. Opt-in via either
    # ``task_run.workspace_config['strategy']`` (project-level) or
    # ``phase_config['params']['workspace_strategy']`` (per-template).
    # When set we create a fresh worktree off the base clone, point the
    # rest of the pipeline at it, and remember the paths so finalization
    # can tear it down idempotently.
    strategy = _resolve_workspace_strategy(ws_cfg, phase_config)
    # When operating on the operator's own checkout, default to worktree
    # isolation. Without this, two concurrent runs would both check out
    # branches on the user's working tree and stomp on each other.
    if local_path and strategy != "worktree":
        await _log("local_path is set — forcing workspace_strategy=worktree for isolation")
        strategy = "worktree"
    if strategy == "worktree":
        base_clone = workspace
        paths = make_worktree_paths(project_root=base_clone, run_id=task_run.id)
        await _log(
            f"Creating worktree {paths.worktree_dir} on branch {paths.branch} "
            f"(strategy=worktree)"
        )
        manager = WorktreeManager(ssh, worker_user=worker_user if needs_user_drop else None)
        await manager.create(paths)

        # Re-chown the new worktree so the worker user owns it (git
        # worktree add inherits the caller's uid). This is always safe
        # even with ``local_path`` — the worktree dir is new.
        if needs_user_drop:
            user_quoted = shlex.quote(worker_user)
            await ssh.run_command(
                f"chown -R {user_quoted}:{user_quoted} {shlex.quote(paths.worktree_dir)}",
                timeout=60,
            )

        # Mutate the run so every downstream phase sees the worktree as
        # *the* workspace + uses the per-run branch when committing.
        task_run.workspace_path = paths.worktree_dir
        task_run.branch_name = paths.branch
        workspace_result["base_clone_path"] = base_clone
        workspace_result["workspace_path"] = paths.worktree_dir
        workspace_result["worktree_paths"] = {
            "branch": paths.branch,
            "worktree_dir": paths.worktree_dir,
            "project_root": paths.project_root,
        }
        # Pass the worktree to readiness checks below.
        workspace = paths.worktree_dir
        await _log(f"Worktree active: {paths.worktree_dir}")

    task_run.workspace_result = workspace_result
    await session.commit()
    await _log(f"Workspace cloned: {len(repos_cloned)} repo(s)")

    # --- Workspace readiness validation ---
    await _validate_readiness(task_run, session, ssh, workspace, worker_user, ws_cfg, _log)


def _resolve_workspace_strategy(ws_cfg: dict, phase_config: dict | None) -> str:
    """Return the workspace strategy for this run, default ``shared_clone``.

    Priority (most specific wins):
    1. ``task_run.workspace_config['strategy']`` — project-level
    2. ``phase_config['params']['workspace_strategy']`` — per-template

    Anything other than ``"worktree"`` falls through to the existing
    shared-clone behavior so existing templates keep working.
    """
    explicit = (ws_cfg or {}).get("strategy")
    if isinstance(explicit, str) and explicit:
        return explicit
    if phase_config:
        params = phase_config.get("params") or {}
        from_phase = params.get("workspace_strategy")
        if isinstance(from_phase, str) and from_phase:
            return from_phase
    return "shared_clone"


async def _validate_readiness(
    task_run: TaskRun,
    session: AsyncSession,
    ssh: CommandExecutor,
    workspace: str,
    worker_user: str | None,
    ws_cfg: dict,
    _log: LogFn,
) -> None:
    """Run workspace readiness checks; raise on failure with fix guide."""
    readiness_repo = WorkspaceReadinessRepository(session)
    server_id = task_run.workspace_server_id
    if not server_id:
        await _log("No workspace server assigned, skipping readiness check")
        return

    if await readiness_repo.is_valid(task_run.project_id, server_id):
        await _log("Workspace readiness: cached validation still valid, skipping checks")
        return

    await _log("Running workspace readiness validation...")
    dev_commands = ws_cfg.get("dev_commands")
    svc = WorkspaceReadinessService(ssh, worker_user=worker_user)
    result = await svc.validate(workspace, dev_commands=dev_commands)

    now = datetime.now(UTC)
    await readiness_repo.upsert(
        task_run.project_id,
        server_id,
        {
            "validation_status": "passed" if result.passed else "failed",
            "validated_at": now,
            "expires_at": (now + timedelta(days=TTL_DAYS)) if result.passed else None,
            "check_results": [asdict(c) for c in result.checks],
            "validation_report": result.report_dict(),
        },
    )

    if not result.passed:
        guide = format_fix_guide(result)
        await _log(guide, level="error")
        raise RuntimeError(f"Workspace not ready: {result.summary}\n\n{guide}")

    await _log(f"Workspace readiness: all {len(result.checks)} checks passed")


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
    ssh: CommandExecutor,
    _log: LogFn,
    project_token: str | None = None,
) -> None:
    await _log("Initializing git repository")
    await remote_git.run_git(["init"], cwd=workspace)
    await remote_git.run_git(["checkout", "-b", task_run.default_branch], cwd=workspace)

    scaffold_template = ws_cfg.get("scaffold_template")
    if scaffold_template:
        await _log(f"Running scaffold template: {scaffold_template}")
        script = f"/opt/agentickode/docker/sandboxes/{scaffold_template}/scaffold.sh"
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

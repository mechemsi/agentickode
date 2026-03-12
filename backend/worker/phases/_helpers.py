# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Shared helpers for worker phases."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import DEFAULT_COST_RATE, MODEL_COST_RATES
from backend.models import PhaseExecution, ProjectConfig, TaskRun, WorkspaceServer
from backend.models.agents import AgentSettings
from backend.services.adapters.cli_adapter import CLIAdapter
from backend.services.adapters.cli_commands import AGENT_COMMANDS
from backend.services.adapters.protocol import RoleAdapter
from backend.services.encryption import decrypt_value
from backend.services.git import GitAccessService
from backend.services.git import ops as git_ops
from backend.services.workspace.agent_install_service import AgentInstallService
from backend.services.workspace.ssh_service import SSHService
from backend.services.workspace.worker_user_service import WorkerUserService

logger = logging.getLogger("autodev.phases.helpers")

_default_roles: dict[str, str] | None = None
_default_modes: dict[str, str] | None = None


def _load_defaults() -> None:
    """Populate default role/mode dicts from the phase registry (lazy)."""
    global _default_roles, _default_modes
    if _default_roles is not None:
        return
    from backend.worker.phases.registry import discover_phases

    phases = discover_phases()
    _default_roles = {n: i.default_role for n, i in phases.items() if i.default_role}
    _default_modes = {n: i.default_agent_mode for n, i in phases.items() if i.default_agent_mode}


def get_agent_mode(phase_name: str, phase_config: dict | None) -> str:
    """Return 'generate' or 'task' for the phase.

    Explicit phase_config['agent_mode'] wins, else use registry defaults.
    Falls back to 'generate' for unknown phases.
    """
    if phase_config:
        mode = phase_config.get("agent_mode")
        if mode in ("generate", "task"):
            return mode
    _load_defaults()
    assert _default_modes is not None
    return _default_modes.get(phase_name, "generate")


def phase_uses_agent(phase_name: str, phase_config: dict | None) -> bool:
    """Decide whether a phase should invoke an AI agent.

    If *phase_config* contains an explicit ``uses_agent`` value, that wins.
    Otherwise fall back to the registry default: only phases with a
    ``default_role`` in their PHASE_META use an agent.
    """
    if phase_config is not None:
        flag = phase_config.get("uses_agent")
        if flag is not None:
            return bool(flag)
    _load_defaults()
    assert _default_roles is not None
    return phase_name in _default_roles


def get_phase_role(
    phase_name: str,
    phase_config: dict | None,
    phase_execution: PhaseExecution | None = None,
) -> str:
    """Return the role to use for a phase.

    Priority: PhaseExecution.agent_override (DB column) > phase_config["role"] > default mapping.
    """
    if phase_execution and phase_execution.agent_override:
        return str(phase_execution.agent_override)
    if phase_config and phase_config.get("role"):
        return str(phase_config["role"])
    _load_defaults()
    assert _default_roles is not None
    return _default_roles.get(phase_name, phase_name)


async def get_workspace_server_id(task_run: TaskRun, session: AsyncSession) -> int | None:
    """Resolve workspace_server_id from the task run's project config."""
    stmt = select(ProjectConfig.workspace_server_id).where(
        ProjectConfig.project_id == task_run.project_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_workspace_server(task_run: TaskRun, session: AsyncSession) -> WorkspaceServer:
    """Resolve the full WorkspaceServer model for a task run.

    Raises ValueError if no workspace server is configured.
    """
    stmt = (
        select(ProjectConfig)
        .options(selectinload(ProjectConfig.workspace_server))
        .where(ProjectConfig.project_id == task_run.project_id)
    )
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()

    if project is None:
        raise ValueError(f"No project config for project_id={task_run.project_id}")
    if project.workspace_server is None:
        raise ValueError(f"No workspace server configured for project {task_run.project_id}")
    return project.workspace_server


async def get_ssh_for_run(task_run: TaskRun, session: AsyncSession) -> SSHService:
    """Create an SSHService connected to the task run's workspace server."""
    server = await get_workspace_server(task_run, session)
    return SSHService.for_server(server)


async def get_project_token(task_run: TaskRun, session: AsyncSession) -> str | None:
    """Decrypt and return the per-project git provider token, if set."""
    stmt = select(ProjectConfig.git_provider_token_enc).where(
        ProjectConfig.project_id == task_run.project_id
    )
    result = await session.execute(stmt)
    enc = result.scalar_one_or_none()
    if not enc:
        return None
    try:
        return decrypt_value(enc)
    except Exception:
        logger.warning("Failed to decrypt git_provider_token for project %s", task_run.project_id)
        return None


async def get_auth_url(
    repo_url: str,
    git_provider: str,
    ssh: SSHService,
    token_override: str | None = None,
) -> tuple[str, str]:
    """Get authenticated git URL. SSH-first, HTTPS-token fallback.

    Returns (url, method) where method is "ssh" or "https".
    When *token_override* is provided it is used instead of the global token.
    """
    gas = GitAccessService(ssh)
    key_info = await gas.get_public_key()
    if key_info.has_key:
        ssh_url = git_ops.to_ssh_url(repo_url)
        if ssh_url:
            return ssh_url, "ssh"
    return git_ops.inject_git_credentials(
        repo_url, git_provider, token_override=token_override
    ), "https"


# Type alias for log callback used by phases
LogFn = Callable[[str, str], Awaitable[None]]


async def _default_log(msg: str, level: str = "info") -> None:
    logger.log(logging.INFO if level == "info" else logging.WARNING, msg)


async def ensure_agent_ready(
    adapter: RoleAdapter,
    log_fn: LogFn | None = None,
    agent_settings: AgentSettings | None = None,
) -> None:
    """Ensure a CLI agent is installed on the worker user and ready to run.

    Flow for agents with ``needs_non_root`` (all CLI agents):
    1. Ensure the worker OS user exists (config/SSH keys copied).
    2. Check if the agent is already installed for the worker user.
    3. If missing, install directly as the worker user via ``runuser``.

    Uses DB-sourced AgentSettings when provided; falls back to hardcoded defaults.
    Does nothing for non-CLI adapters (Ollama, OpenHands).
    """
    if not isinstance(adapter, CLIAdapter):
        return

    _log = log_fn or _default_log
    agent = adapter.agent_name
    ssh = adapter.ssh

    # Resolve check command and needs_non_root from DB settings.
    if agent_settings and agent_settings.check_cmd:
        check_cmd = agent_settings.check_cmd
        needs_non_root = agent_settings.needs_non_root
    elif agent in AGENT_COMMANDS:
        check_cmd = str(AGENT_COMMANDS[agent].get("check", ""))
        needs_non_root = True  # Default all CLI agents to non-root
    else:
        return

    if needs_non_root and ssh.username == "root":
        # --- Install directly on the worker user ---
        user_svc = WorkerUserService(ssh)
        username = adapter.worker_user or "coder"

        # Step 1: Ensure worker user exists with config/credentials
        await _log(f"Ensuring worker user '{username}' exists for {agent}", "info")
        info = await user_svc.setup(username)
        if not info.exists:
            raise RuntimeError(f"Failed to create worker user: {info.error}")

        # Step 2: Check if agent already installed for worker user
        if agent not in info.agents:
            await _log(
                f"Agent '{agent}' not found for worker user '{username}', installing...",
                "info",
            )
            install_svc = AgentInstallService(
                ssh, agent_settings=[agent_settings] if agent_settings else []
            )
            result = await install_svc.install_agent(agent, as_user=username)
            if not result.success:
                raise RuntimeError(f"Install of {agent} as '{username}' failed: {result.error}")
            await _log(f"Agent '{agent}' installed for worker user '{username}'", "info")

            # Verify it's now available
            info = await user_svc.check_status(username)

        if agent in info.agents:
            await _log(f"Worker user '{username}' ready with {agent}", "info")
            adapter.worker_user = username
        else:
            raise RuntimeError(
                f"{agent} still not available for worker user '{username}' "
                f"after install. Available: {info.agents}"
            )
    else:
        # Non-root SSH user or agent doesn't need non-root: install directly
        _, _, rc = await ssh.run_command(check_cmd, timeout=10)
        if rc != 0:
            await _log(f"Agent '{agent}' not found, auto-installing...", "info")
            install_svc = AgentInstallService(
                ssh, agent_settings=[agent_settings] if agent_settings else []
            )
            result = await install_svc.install_agent(agent)
            if not result.success:
                raise RuntimeError(f"Auto-install of {agent} failed: {result.error}")
            await _log(f"Agent '{agent}' installed successfully", "info")


def get_agent_settings_kwargs(
    agent_settings: object | None, phase_config: dict | None = None
) -> dict:
    """Extract runtime kwargs from AgentSettings, with per-phase overrides.

    Merge order: AgentSettings (global DB) → phase_config (per-phase, wins).
    Returns a dict with cli_flags, environment_vars, and timeout if set.
    These can be unpacked into adapter.run_task() or adapter.generate() calls.
    """
    kwargs: dict = {}

    # Layer 1: agent-level settings
    if agent_settings is not None:
        cli_flags = getattr(agent_settings, "cli_flags", None)
        if cli_flags:
            kwargs["cli_flags"] = dict(cli_flags)
        env_vars = getattr(agent_settings, "environment_vars", None)
        if env_vars:
            kwargs["environment_vars"] = dict(env_vars)
        timeout = getattr(agent_settings, "default_timeout", None)
        if timeout:
            kwargs["timeout"] = timeout

    # Layer 2: phase-level overrides (shallow merge for dicts, replace for scalar)
    if phase_config is not None:
        phase_flags = phase_config.get("cli_flags")
        if phase_flags:
            kwargs["cli_flags"] = {**kwargs.get("cli_flags", {}), **phase_flags}
        phase_env = phase_config.get("environment_vars")
        if phase_env:
            kwargs["environment_vars"] = {**kwargs.get("environment_vars", {}), **phase_env}
        phase_timeout = phase_config.get("timeout_seconds")
        if phase_timeout is not None:
            kwargs["timeout"] = phase_timeout

    return kwargs


def apply_phase_command_overrides(adapter: RoleAdapter, phase_config: dict | None) -> None:
    """Apply per-phase command_templates overrides to a CLIAdapter.

    No-op for non-CLI adapters or when phase_config has no command_templates.
    """
    if phase_config is None:
        return
    overrides = phase_config.get("command_templates")
    if not overrides:
        return
    if isinstance(adapter, CLIAdapter):
        adapter.apply_command_overrides(overrides)


def estimate_cost(
    agent_name: str, prompt_chars: int, response_chars: int
) -> tuple[int, int, float]:
    """Estimate tokens and cost from char counts.

    Returns (tokens_in, tokens_out, cost_usd).
    """
    tokens_in = prompt_chars // 4
    tokens_out = response_chars // 4
    base = agent_name.split("/")[0]
    rate_in, rate_out = MODEL_COST_RATES.get(base, DEFAULT_COST_RATE)
    cost = (tokens_in * rate_in + tokens_out * rate_out) / 1_000_000
    return tokens_in, tokens_out, round(cost, 6)


def get_token_usage(
    adapter: RoleAdapter,
    agent_name: str,
    prompt_chars: int,
    response_chars: int,
) -> tuple[int, int, float, str]:
    """Get token counts and cost, preferring actual API counts over estimates.

    Checks adapter.last_token_usage for actual counts from the LLM API.
    Falls back to estimate_cost() for adapters that don't track usage.

    Returns (tokens_in, tokens_out, cost_usd, source) where source is
    "api" (actual counts) or "estimated".
    """
    usage = getattr(adapter, "last_token_usage", None)
    if isinstance(usage, tuple) and len(usage) == 2:
        tokens_in, tokens_out = usage
        base = agent_name.split("/")[0]
        rate_in, rate_out = MODEL_COST_RATES.get(base, DEFAULT_COST_RATE)
        cost = (tokens_in * rate_in + tokens_out * rate_out) / 1_000_000
        return tokens_in, tokens_out, round(cost, 6), "api"

    tokens_in, tokens_out, cost = estimate_cost(agent_name, prompt_chars, response_chars)
    return tokens_in, tokens_out, cost, "estimated"


async def close_run_session(task_run: TaskRun, db_session: AsyncSession) -> None:
    """Close any agent session associated with this task run.

    Extracts session_id from coding_results (or planning_result) and calls
    close_session() on a CLIAdapter to release locks. Safe to call even
    when there is no session — it's a no-op in that case.
    """
    session_id: str | None = None
    for result_attr in ("coding_results", "planning_result", "review_result"):
        data = getattr(task_run, result_attr, None)
        if isinstance(data, dict):
            sid = data.get("session_id")
            if sid and isinstance(sid, str):
                session_id = sid
                break

    if not session_id:
        return

    try:
        ssh = await get_ssh_for_run(task_run, db_session)
        adapter = CLIAdapter(
            ssh_service=ssh,
            agent_name="claude",
            server_name="cleanup",
        )
        await adapter.close_session(session_id, task_run.workspace_path)
        logger.info("Closed agent session %s for run #%d", session_id[:8], task_run.id)
    except Exception:
        logger.debug("Session cleanup failed for run #%d (non-fatal)", task_run.id, exc_info=True)
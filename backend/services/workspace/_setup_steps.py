# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Individual setup step implementations for workspace server setup."""

from __future__ import annotations

import logging
import shlex
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import DiscoveredAgent
from backend.models.agents import AgentSettings
from backend.repositories.app_setting_repo import AppSettingRepository
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.services.git import GitAccessService
from backend.services.workspace.agent_discovery import AgentDiscoveryService
from backend.services.workspace.agent_install_service import AgentInstallService
from backend.services.workspace.project_discovery import ProjectDiscoveryService
from backend.services.workspace.ssh_service import SSHService
from backend.services.workspace.worker_user_service import WorkerUserService

logger = logging.getLogger("agentickode.server_setup")

# Step name -> handler function mapping (populated at module level below)
_STEP_HANDLERS: dict[str, Any] = {}


async def _step_ssh_test(
    server: Any, ssh: SSHService, session: AsyncSession, setup_password: str | None
) -> None:
    repo = WorkspaceServerRepository(session)
    result = await ssh.test_connection()
    if not result.success and setup_password:
        logger.info("Key auth failed for %s, deploying key via password...", server.hostname)
        deploy_result = await ssh.deploy_key(setup_password)
        if not deploy_result.success:
            raise RuntimeError(
                f"SSH key auth failed and key deployment failed: {deploy_result.error}"
            )
        result = deploy_result
    if not result.success:
        hint = " — provide the setup password to deploy the SSH key" if not setup_password else ""
        raise RuntimeError(f"SSH connection failed: {result.error}{hint}")
    await repo.update(server, {"last_seen_at": datetime.now(UTC)})


async def _step_install_system_deps(
    server: Any, ssh: SSHService, session: AsyncSession, setup_password: str | None
) -> None:
    username = server.worker_user or "coder"
    await _install_system_deps(ssh, server.id, username)


async def _step_create_worker_user(
    server: Any, ssh: SSHService, session: AsyncSession, setup_password: str | None
) -> None:
    repo = WorkspaceServerRepository(session)
    username = server.worker_user or "coder"
    wus = WorkerUserService(ssh)
    info = await wus.check_status(username)
    if info.exists:
        logger.info(
            "Worker user '%s' already exists on %s, skipping creation",
            username,
            server.hostname,
        )
    else:
        info = await wus.setup(username)
        if not info.exists:
            raise RuntimeError(info.error or "Failed to create worker user")
    await repo.update(
        server,
        {
            "worker_user": username,
            "worker_user_status": "ready",
            "worker_user_error": None,
        },
    )


async def _step_create_workspace_dir(
    server: Any, ssh: SSHService, session: AsyncSession, setup_password: str | None
) -> None:
    repo = WorkspaceServerRepository(session)
    username = server.worker_user or "coder"
    home = f"/home/{username}"
    default_ws = f"{home}/workspaces"
    ws_dir = (
        server.workspace_root
        if server.workspace_root and server.workspace_root != "/workspaces"
        else default_ws
    )
    _, _, rc_check = await ssh.run_command(f"test -d {ws_dir}", timeout=10)
    if rc_check == 0:
        logger.info("Workspace dir %s already exists on %s, skipping", ws_dir, server.hostname)
    else:
        _, stderr, rc = await ssh.run_command(
            f"mkdir -p {ws_dir} && chown {username}:{username} {ws_dir}",
            timeout=15,
        )
        if rc != 0:
            raise RuntimeError(f"Failed to create workspace dir: {stderr.strip()}")
    await repo.update(server, {"workspace_root": ws_dir})


async def _step_install_agents(
    server: Any, ssh: SSHService, session: AsyncSession, setup_password: str | None
) -> None:
    username = server.worker_user or "coder"
    settings_repo = AppSettingRepository(session)
    default_agents = await settings_repo.get("default_agents")
    if default_agents:
        result = await session.execute(select(AgentSettings))
        all_settings = list(result.scalars().all())
        installer = AgentInstallService(ssh, all_settings)
        for agent_name in default_agents:
            install_result = await installer.install_agent(agent_name, as_user=username)
            if not install_result.success:
                logger.warning(
                    "Agent %s install failed on server %d: %s",
                    agent_name,
                    server.id,
                    install_result.error,
                )


async def _step_sync_agents(
    server: Any, ssh: SSHService, session: AsyncSession, setup_password: str | None
) -> None:
    username = server.worker_user or "coder"
    wus = WorkerUserService(ssh)
    await wus.sync_agents(username)
    user_failed = await _install_user_deps(ssh, username)
    if user_failed:
        logger.warning(
            "User-level deps issues on server %d: %s",
            server.id,
            "; ".join(user_failed),
        )


async def _step_generate_ssh_key(
    server: Any, ssh: SSHService, session: AsyncSession, setup_password: str | None
) -> None:
    gas = GitAccessService(ssh)
    await gas.generate_key(server.name)


async def _step_discover(
    server: Any, ssh: SSHService, session: AsyncSession, setup_password: str | None
) -> None:
    repo = WorkspaceServerRepository(session)
    username = server.worker_user or "coder"
    discovery = AgentDiscoveryService(ssh)

    admin_infos = await discovery.discover_all()
    admin_agents = [
        DiscoveredAgent(
            agent_name=a.agent_name,
            agent_type=a.agent_type,
            path=a.path,
            version=a.version,
            available=a.available,
            metadata_=a.metadata,
        )
        for a in admin_infos
    ]
    await repo.replace_agents_for_context(server.id, "admin", admin_agents)

    worker_infos = await discovery.discover_all(as_user=username)
    worker_agents = [
        DiscoveredAgent(
            agent_name=a.agent_name,
            agent_type=a.agent_type,
            path=a.path,
            version=a.version,
            available=a.available,
            metadata_=a.metadata,
        )
        for a in worker_infos
    ]
    await repo.replace_agents_for_context(server.id, "worker", worker_agents)

    proj_discovery = ProjectDiscoveryService(ssh)
    workspace_root = server.workspace_root or f"/home/{username}/workspaces"
    await proj_discovery.scan_workspace(workspace_root)


async def _step_mark_online(
    server: Any, ssh: SSHService, session: AsyncSession, setup_password: str | None
) -> None:
    repo = WorkspaceServerRepository(session)
    await repo.update(
        server,
        {"status": "online", "error_message": None, "last_seen_at": datetime.now(UTC)},
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------
_STEP_HANDLERS = {
    "ssh_test": _step_ssh_test,
    "install_system_deps": _step_install_system_deps,
    "create_worker_user": _step_create_worker_user,
    "create_workspace_dir": _step_create_workspace_dir,
    "install_agents": _step_install_agents,
    "sync_agents": _step_sync_agents,
    "generate_ssh_key": _step_generate_ssh_key,
    "discover": _step_discover,
    "mark_online": _step_mark_online,
}


async def execute_step(
    session_factory: Any,
    server_id: int,
    step_name: str,
    *,
    setup_password: str | None = None,
) -> None:
    """Execute a single setup step for the given server."""
    handler = _STEP_HANDLERS.get(step_name)
    if not handler:
        raise ValueError(f"Unknown setup step: {step_name}")

    async with session_factory() as session:
        repo = WorkspaceServerRepository(session)
        server = await repo.get_by_id(server_id)
        if not server:
            raise RuntimeError(f"Server {server_id} not found")

        ssh = SSHService.for_server(server)
        await handler(server, ssh, session, setup_password)


# ---------------------------------------------------------------------------
# Dependency installation helpers
# ---------------------------------------------------------------------------


async def _install_system_deps(ssh: SSHService, server_id: int, username: str) -> None:
    """Install system-level deps as root, then user-level deps if user exists."""
    failed: list[str] = []

    apt_cmd = (
        "apt-get update -qq && "
        "apt-get install -y -qq git ca-certificates curl pipx unzip "
        "libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 "
        "libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 "
        "libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 "
        "libcairo2 libasound2 libwayland-client0 "
        "2>/dev/null"
    )
    _, stderr, rc = await ssh.run_command(apt_cmd, timeout=120)
    if rc != 0:
        failed.append(f"apt packages: {stderr.strip()[:500]}")

    # Install GitHub CLI (gh) for PR creation from workspace servers
    # Clean up any malformed sources list from previous attempts
    gh_cmd = (
        "rm -f /etc/apt/sources.list.d/github-cli.list 2>/dev/null; "
        "if ! command -v gh >/dev/null 2>&1; then "
        "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg "
        "-o /usr/share/keyrings/githubcli-archive-keyring.gpg && "
        "chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && "
        'printf "deb [arch=%s signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg]'
        ' https://cli.github.com/packages stable main\\n" '
        '"$(dpkg --print-architecture)" > /etc/apt/sources.list.d/github-cli.list && '
        "apt-get update -qq && apt-get install -y -qq gh 2>/dev/null; "
        "fi"
    )
    _, stderr, rc = await ssh.run_command(gh_cmd, timeout=120)
    if rc != 0:
        failed.append(f"gh cli: {stderr.strip()[:500]}")

    node_cmd = (
        "if ! command -v node >/dev/null 2>&1; then "
        "curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && "
        "apt-get install -y -qq nodejs 2>/dev/null; "
        "fi"
    )
    _, stderr, rc = await ssh.run_command(node_cmd, timeout=120)
    if rc != 0:
        failed.append(f"nodejs: {stderr.strip()[:500]}")

    pw_cmd = "npm install -g playwright && playwright install --with-deps chrome"
    stdout, stderr, rc = await ssh.run_command(pw_cmd, timeout=300)
    if rc != 0:
        err = stderr.strip() or stdout.strip()
        failed.append(f"playwright: {err[:500]}")

    safe_user = shlex.quote(username)
    _, _, rc = await ssh.run_command(f"id -u {safe_user}", timeout=10)
    if rc == 0:
        user_failed = await _install_user_deps(ssh, username)
        failed.extend(user_failed)
    else:
        logger.info(
            "Worker user '%s' not yet created on server %d, "
            "user-level deps will install in sync_agents step",
            username,
            server_id,
        )

    if failed:
        msg = "; ".join(failed)
        logger.warning("System deps issues on server %d: %s", server_id, msg)
        raise RuntimeError(f"Some dependencies failed to install: {msg}")


async def _install_user_deps(ssh: SSHService, username: str) -> list[str]:
    """Install bun, playwright chrome as worker user. Returns list of failures."""
    failed: list[str] = []
    safe_user = shlex.quote(username)
    home = f"/home/{username}"

    def _as_user(cmd: str) -> str:
        user_path = f"{home}/.local/bin:{home}/.bun/bin:/usr/local/bin:/usr/bin:/bin"
        inner = (
            f"export HOME={home} && "
            f"export PATH={shlex.quote(user_path)} && "
            f"export npm_config_cache={home}/.npm && "
            f"export XDG_CONFIG_HOME={home}/.config && "
            f"cd {home} && "
            f"{cmd}"
        )
        return f"runuser -l {safe_user} -c {shlex.quote(inner)}"

    bun_cmd = _as_user(
        "if ! command -v bun >/dev/null 2>&1; then "
        "curl -fsSL https://bun.sh/install | bash; "
        "fi"
    )
    stdout, stderr, rc = await ssh.run_command(bun_cmd, timeout=60)
    if rc != 0:
        err = stderr.strip() or stdout.strip()
        failed.append(f"bun: {err[:500]}")

    checks = [
        ("node", "node --version"),
        ("npm", "npm --version"),
        ("bun", "bun --version"),
        ("playwright", "playwright --version"),
    ]
    missing: list[str] = []
    for name, cmd in checks:
        _, _, rc = await ssh.run_command(_as_user(cmd), timeout=10)
        if rc != 0:
            missing.append(name)
    if missing:
        failed.append(f"not available for {username}: {', '.join(missing)}")

    return failed

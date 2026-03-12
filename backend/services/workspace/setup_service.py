# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Async server setup orchestrator — runs after a workspace server is added."""

from __future__ import annotations

import asyncio
import logging
import shlex
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

logger = logging.getLogger("autodev.server_setup")

SETUP_STEPS = [
    "ssh_test",
    "install_system_deps",
    "create_worker_user",
    "create_workspace_dir",
    "install_agents",
    "sync_agents",
    "generate_ssh_key",
    "discover",
    "mark_online",
]


def _step_entry(status: str = "pending", error: str | None = None) -> dict[str, Any]:
    return {"status": status, "error": error, "timestamp": datetime.now(UTC).isoformat()}


def _get_setup_log(server: Any) -> dict[str, Any]:
    raw = server.setup_log
    return dict(raw) if raw else {}  # type: ignore[arg-type]


class ServerSetupService:
    """Orchestrates async server setup after creation."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    def kick_off_setup(
        self, server_id: int, *, setup_password: str | None = None
    ) -> asyncio.Task[None]:
        """Launch async setup in background, returns the task handle."""
        return asyncio.create_task(self._run_setup(server_id, setup_password=setup_password))

    async def retry_setup(self, server_id: int) -> None:
        """Re-run setup from the first failed step."""
        await self._run_setup(server_id, retry=True)

    async def _run_setup(
        self, server_id: int, *, retry: bool = False, setup_password: str | None = None
    ) -> None:
        try:
            async with self._session_factory() as session:
                repo = WorkspaceServerRepository(session)
                server = await repo.get_by_id(server_id)
                if not server:
                    logger.error("Server %d not found for setup", server_id)
                    return

                # Initialize or resume setup_log
                setup_log: dict[str, Any] = _get_setup_log(server)
                if not retry:
                    setup_log = {step: _step_entry() for step in SETUP_STEPS}
                start_from = self._find_resume_step(setup_log) if retry else 0

                await repo.update(
                    server,
                    {"status": "setting_up", "setup_log": setup_log, "error_message": None},
                )

            # Run each step
            for i, step_name in enumerate(SETUP_STEPS):
                if i < start_from:
                    continue
                try:
                    async with self._session_factory() as session:
                        repo = WorkspaceServerRepository(session)
                        server = await repo.get_by_id(server_id)
                        if not server:
                            return
                        setup_log = _get_setup_log(server)
                        setup_log[step_name] = _step_entry("running")
                        await repo.update(server, {"setup_log": setup_log})

                    await self._execute_step(server_id, step_name, setup_password=setup_password)

                    async with self._session_factory() as session:
                        repo = WorkspaceServerRepository(session)
                        server = await repo.get_by_id(server_id)
                        if not server:
                            return
                        setup_log = _get_setup_log(server)
                        setup_log[step_name] = _step_entry("completed")
                        await repo.update(server, {"setup_log": setup_log})

                except Exception as exc:
                    logger.exception("Setup step %s failed for server %d", step_name, server_id)
                    async with self._session_factory() as session:
                        repo = WorkspaceServerRepository(session)
                        server = await repo.get_by_id(server_id)
                        if not server:
                            return
                        setup_log = _get_setup_log(server)
                        setup_log[step_name] = _step_entry("failed", str(exc))
                        await repo.update(
                            server,
                            {
                                "status": "setup_failed",
                                "error_message": f"Step '{step_name}' failed: {exc}",
                                "setup_log": setup_log,
                            },
                        )
                    return

        except Exception:
            logger.exception("Unexpected error during setup for server %d", server_id)

    async def _execute_step(
        self, server_id: int, step_name: str, *, setup_password: str | None = None
    ) -> None:
        async with self._session_factory() as session:
            repo = WorkspaceServerRepository(session)
            server = await repo.get_by_id(server_id)
            if not server:
                raise RuntimeError(f"Server {server_id} not found")

            ssh = SSHService.for_server(server)
            username = server.worker_user or "coder"

            if step_name == "ssh_test":
                result = await ssh.test_connection()
                if not result.success and setup_password:
                    # Key auth failed — deploy key using password, then re-test
                    logger.info(
                        "Key auth failed for %s, deploying key via password...", server.hostname
                    )
                    deploy_result = await ssh.deploy_key(setup_password)
                    if not deploy_result.success:
                        raise RuntimeError(
                            f"SSH key auth failed and key deployment failed: {deploy_result.error}"
                        )
                    result = deploy_result
                if not result.success:
                    hint = (
                        " — provide the setup password to deploy the SSH key"
                        if not setup_password
                        else ""
                    )
                    raise RuntimeError(f"SSH connection failed: {result.error}{hint}")
                await repo.update(server, {"last_seen_at": datetime.now(UTC)})

            elif step_name == "install_system_deps":
                await self._install_system_deps(ssh, server_id, username)

            elif step_name == "create_worker_user":
                wus = WorkerUserService(ssh)
                # Check if user already exists (e.g. added by another instance)
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

            elif step_name == "create_workspace_dir":
                home = f"/home/{username}"
                # Use custom workspace_root if set (e.g. server already configured)
                default_ws = f"{home}/workspaces"
                ws_dir = (
                    server.workspace_root
                    if server.workspace_root and server.workspace_root != "/workspaces"
                    else default_ws
                )
                # Check if workspace dir already exists
                _, _, rc_check = await ssh.run_command(f"test -d {ws_dir}", timeout=10)
                if rc_check == 0:
                    logger.info(
                        "Workspace dir %s already exists on %s, skipping", ws_dir, server.hostname
                    )
                else:
                    _, stderr, rc = await ssh.run_command(
                        f"mkdir -p {ws_dir} && chown {username}:{username} {ws_dir}",
                        timeout=15,
                    )
                    if rc != 0:
                        raise RuntimeError(f"Failed to create workspace dir: {stderr.strip()}")
                await repo.update(server, {"workspace_root": ws_dir})

            elif step_name == "install_agents":
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
                                server_id,
                                install_result.error,
                            )

            elif step_name == "sync_agents":
                wus = WorkerUserService(ssh)
                await wus.sync_agents(username)
                # Install user-level deps (bun, playwright) if missed during system_deps
                user_failed = await self._install_user_deps(ssh, username)
                if user_failed:
                    logger.warning(
                        "User-level deps issues on server %d: %s",
                        server_id,
                        "; ".join(user_failed),
                    )

            elif step_name == "generate_ssh_key":
                gas = GitAccessService(ssh)
                await gas.generate_key(server.name)

            elif step_name == "discover":
                discovery = AgentDiscoveryService(ssh)

                # Discover admin agents
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

                # Discover worker agents
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

            elif step_name == "mark_online":
                await repo.update(
                    server,
                    {"status": "online", "error_message": None, "last_seen_at": datetime.now(UTC)},
                )

    async def _install_system_deps(self, ssh: SSHService, server_id: int, username: str) -> None:
        """Install system-level deps as root, then user-level deps if user exists."""
        failed: list[str] = []

        # --- System-level deps (as root) ---
        # Include Playwright's system library deps so user-level install doesn't need sudo
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

        # Node.js 22.x LTS (needed for npm-based MCP servers)
        node_cmd = (
            "if ! command -v node >/dev/null 2>&1; then "
            "curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && "
            "apt-get install -y -qq nodejs 2>/dev/null; "
            "fi"
        )
        _, stderr, rc = await ssh.run_command(node_cmd, timeout=120)
        if rc != 0:
            failed.append(f"nodejs: {stderr.strip()[:500]}")

        # Playwright — install as root so it's available system-wide
        pw_cmd = "npm install -g playwright && playwright install --with-deps chrome"
        stdout, stderr, rc = await ssh.run_command(pw_cmd, timeout=300)
        if rc != 0:
            err = stderr.strip() or stdout.strip()
            failed.append(f"playwright: {err[:500]}")

        # User-level deps (bun, playwright) — only if user already exists
        safe_user = shlex.quote(username)
        _, _, rc = await ssh.run_command(f"id -u {safe_user}", timeout=10)
        if rc == 0:
            user_failed = await self._install_user_deps(ssh, username)
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

    async def _install_user_deps(self, ssh: SSHService, username: str) -> list[str]:
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

        # Bun runtime
        bun_cmd = _as_user(
            "if ! command -v bun >/dev/null 2>&1; then "
            "curl -fsSL https://bun.sh/install | bash; "
            "fi"
        )
        stdout, stderr, rc = await ssh.run_command(bun_cmd, timeout=60)
        if rc != 0:
            err = stderr.strip() or stdout.strip()
            failed.append(f"bun: {err[:500]}")

        # Verify deps available as worker user
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

    @staticmethod
    def _find_resume_step(setup_log: dict[str, Any]) -> int:
        """Find the index of the first non-completed step."""
        for i, step in enumerate(SETUP_STEPS):
            entry = setup_log.get(step, {})
            if entry.get("status") != "completed":
                return i
        return len(SETUP_STEPS)
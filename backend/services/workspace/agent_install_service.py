# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Service for checking and installing coding agents on workspace servers.

Agent metadata (install commands, check commands, prerequisites) is stored in
the ``AgentSettings`` DB table and seeded on startup via ``backend/seed.py``.
This service receives the DB records via its constructor — no hardcoded agent
definitions live here.
"""

from __future__ import annotations

import shlex
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.services.workspace.agent_discovery import AgentDiscoveryService

if TYPE_CHECKING:
    from backend.models.agents import AgentSettings
    from backend.services.workspace.ssh_service import SSHService


def _cfg_from_settings(s: AgentSettings) -> dict[str, str | bool]:
    """Convert an AgentSettings DB row to an internal config dict."""
    return {
        "display_name": str(s.display_name),
        "description": str(s.description),
        "agent_type": str(s.agent_type or "cli_binary"),
        "check_cmd": str(s.check_cmd or ""),
        "prereq_check": str(s.prereq_check or ""),
        "prereq_name": str(s.prereq_name or ""),
        "install_cmd": str(s.install_cmd or ""),
        "post_install_cmd": str(s.post_install_cmd or ""),
        "needs_non_root": bool(s.needs_non_root),
    }


def _wrap_as_user(cmd: str, username: str) -> str:
    """Wrap a command to run as a specific OS user via runuser."""
    home = f"/home/{username}"
    user_path = (
        f"{home}/.local/bin:{home}/.claude/bin"
        ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )
    # Set HOME, PATH, and GIT_SSH_COMMAND so git SSH operations find the key
    ssh_key = f"{home}/.ssh/id_ed25519"
    git_ssh = (
        f'GIT_SSH_COMMAND="ssh -i {ssh_key} -o StrictHostKeyChecking=accept-new -o BatchMode=yes"'
    )
    # Set NODE_EXTRA_CA_CERTS so Node.js-based tools (Claude CLI) trust system certs
    node_certs = "NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt"
    inner = (
        f"export HOME={home} && "
        f"export PATH={shlex.quote(user_path)} && "
        f"export {git_ssh} && "
        f"export GIT_TERMINAL_PROMPT=0 && "
        f"export {node_certs} && "
        f"cd {home} && "
        f"{cmd}"
    )
    return f"runuser -l {username} -c {shlex.quote(inner)}"


@dataclass
class AgentStatus:
    agent_name: str
    display_name: str
    description: str
    agent_type: str
    installed: bool
    version: str | None = None
    path: str | None = None


@dataclass
class InstallResult:
    success: bool
    agent_name: str
    message: str | None = None
    error: str | None = None
    output: str | None = None


class AgentInstallService:
    """Check and install coding agents on a workspace server.

    Reads agent metadata exclusively from DB records (``AgentSettings``).
    Callers must load records from the database and pass them in.
    """

    def __init__(
        self,
        ssh: SSHService,
        agent_settings: list[AgentSettings],
    ):
        self._ssh = ssh
        self._discovery = AgentDiscoveryService(ssh)
        self._agents: dict[str, dict[str, str | bool]] = {
            s.agent_name: _cfg_from_settings(s) for s in agent_settings
        }

    async def check_all_agents(self, as_user: str | None = None) -> list[AgentStatus]:
        """Return status of all supported agents. If as_user, check as that user."""
        discovered = await self._discovery.discover_all(as_user=as_user)
        discovered_map = {a.agent_name: a for a in discovered}

        results: list[AgentStatus] = []
        for name, cfg in self._agents.items():
            agent = discovered_map.get(name)
            if agent:
                results.append(
                    AgentStatus(
                        agent_name=name,
                        display_name=str(cfg["display_name"]),
                        description=str(cfg["description"]),
                        agent_type=str(cfg["agent_type"]),
                        installed=True,
                        version=agent.version,
                        path=agent.path,
                    )
                )
            else:
                results.append(
                    AgentStatus(
                        agent_name=name,
                        display_name=str(cfg["display_name"]),
                        description=str(cfg["description"]),
                        agent_type=str(cfg["agent_type"]),
                        installed=False,
                    )
                )
        return results

    async def _resync_credentials(self, username: str) -> None:
        """Re-copy auth config from root to worker user after install.

        Install scripts (e.g. ``curl install.sh | bash``) may create a fresh
        config that overwrites the credentials we previously copied.  This
        restores the root-level auth so plugin/marketplace commands succeed.
        """
        safe_user = shlex.quote(username)
        home = f"/home/{username}"
        cmds = [
            f"cp -fL /root/.claude.json {home}/.claude.json 2>/dev/null || true",
            f"mkdir -p {home}/.claude",
            f"cp -rnL /root/.claude/* {home}/.claude/ 2>/dev/null || true",
            f"chown -R {safe_user}:{safe_user} {home}/.claude.json {home}/.claude 2>/dev/null || true",
        ]
        await self._ssh.run_command(" && ".join(cmds), timeout=15)

    async def install_agent(self, agent_name: str, as_user: str | None = None) -> InstallResult:
        """Install an agent on the workspace server.

        If *as_user* is given, all commands (prereq check, install, verify)
        run as that OS user via ``runuser``.  The user must already exist.
        """
        if agent_name not in self._agents:
            return InstallResult(
                success=False,
                agent_name=agent_name,
                error=f"Unknown agent: {agent_name}",
            )

        cfg = self._agents[agent_name]

        def _maybe_wrap(cmd: str) -> str:
            return _wrap_as_user(cmd, as_user) if as_user else cmd

        # Check prerequisite
        prereq_cmd = str(cfg.get("prereq_check", ""))
        if prereq_cmd:
            _, _, rc = await self._ssh.run_command(_maybe_wrap(prereq_cmd), timeout=10)
            if rc != 0:
                return InstallResult(
                    success=False,
                    agent_name=agent_name,
                    error=f"Prerequisite not found: {cfg.get('prereq_name', 'unknown')}",
                )

        # Run install command
        install_cmd = str(cfg.get("install_cmd", ""))
        if not install_cmd:
            return InstallResult(
                success=False,
                agent_name=agent_name,
                error="No install command configured",
            )

        # Ensure auth credentials are in place before install (plugins need auth)
        if as_user:
            await self._resync_credentials(as_user)

        stdout, stderr, rc = await self._ssh.run_command(_maybe_wrap(install_cmd), timeout=300)
        install_output = stdout.strip()
        if rc != 0:
            error_msg = stderr.strip() or stdout.strip() or "Install command failed"
            return InstallResult(
                success=False,
                agent_name=agent_name,
                error=error_msg[:500],
                output=install_output[:5000] if install_output else None,
            )

        # Re-copy auth credentials — install scripts may overwrite config
        if as_user:
            await self._resync_credentials(as_user)

        # Run post-install (plugins, tools — requires auth)
        post_cmd = str(cfg.get("post_install_cmd", ""))
        if post_cmd:
            post_out, post_err, post_rc = await self._ssh.run_command(
                _maybe_wrap(post_cmd), timeout=300
            )
            if post_out.strip():
                install_output += "\n" + post_out.strip()
            if post_rc != 0:
                # Post-install failure is non-fatal — binary is installed
                install_output += f"\n[post-install warnings: {post_err.strip()[:300]}]"

        # Verify installation
        check_cmd = str(cfg.get("check_cmd", ""))
        if check_cmd:
            _, _, rc = await self._ssh.run_command(_maybe_wrap(check_cmd), timeout=10)
            if rc != 0:
                return InstallResult(
                    success=False,
                    agent_name=agent_name,
                    error="Install command succeeded but agent not found after install",
                    output=install_output[:5000] if install_output else None,
                )

        return InstallResult(
            success=True,
            agent_name=agent_name,
            message=f"{cfg['display_name']} installed successfully",
            output=install_output[:5000] if install_output else None,
        )

    async def install_agent_stream(
        self, agent_name: str, as_user: str | None = None
    ) -> AsyncIterator[str]:
        """Install an agent, yielding progress lines as they arrive."""
        if agent_name not in self._agents:
            yield f"[error] Unknown agent: {agent_name}"
            return

        cfg = self._agents[agent_name]

        def _maybe_wrap(cmd: str) -> str:
            return _wrap_as_user(cmd, as_user) if as_user else cmd

        # Check prerequisite
        prereq_cmd = str(cfg.get("prereq_check", ""))
        if prereq_cmd:
            yield f"[step] Checking prerequisites ({cfg.get('prereq_name', '')})..."
            _, _, rc = await self._ssh.run_command(_maybe_wrap(prereq_cmd), timeout=10)
            if rc != 0:
                yield f"[error] Prerequisite not found: {cfg.get('prereq_name', 'unknown')}"
                return
            yield "[ok] Prerequisites satisfied"

        # Run install command
        install_cmd = str(cfg.get("install_cmd", ""))
        if not install_cmd:
            yield "[error] No install command configured"
            return

        # Ensure auth credentials are in place before install (plugins need auth)
        if as_user:
            yield "[step] Syncing credentials..."
            await self._resync_credentials(as_user)
            yield "[ok] Credentials synced"

        yield f"[step] Installing {cfg['display_name']}..."
        async for line in self._ssh.run_command_stream(_maybe_wrap(install_cmd), timeout=300):
            yield line

        # Re-copy credentials in case install script overwrote config
        if as_user:
            yield "[step] Re-syncing credentials..."
            await self._resync_credentials(as_user)
            yield "[ok] Credentials synced"

        # Run post-install (plugins, tools — requires auth)
        post_cmd = str(cfg.get("post_install_cmd", ""))
        if post_cmd:
            yield "[step] Running post-install (plugins & tools)..."
            async for line in self._ssh.run_command_stream(_maybe_wrap(post_cmd), timeout=300):
                yield line

        # Verify installation
        check_cmd = str(cfg.get("check_cmd", ""))
        if check_cmd:
            yield "[step] Verifying installation..."
            _, _, rc = await self._ssh.run_command(_maybe_wrap(check_cmd), timeout=10)
            if rc != 0:
                yield "[error] Install command succeeded but agent not found after install"
                return
            yield "[ok] Agent verified"

        yield f"[done] {cfg['display_name']} installed successfully"

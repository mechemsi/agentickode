# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""WorkerUserService — manages non-root OS users on workspace servers."""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from backend.config import settings

if TYPE_CHECKING:
    from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("autodev.worker_user")

# Agents that need non-root to run (used by CLIAdapter)
_CLI_AGENTS = ["claude", "codex", "aider", "opencode", "gemini", "kimi", "copilot"]


@dataclass
class WorkerUserInfo:
    exists: bool
    username: str
    agents: list[str]
    error: str | None = None


class WorkerUserService:
    """Manages non-root OS users on a remote workspace server via SSH."""

    def __init__(self, ssh: SSHService):
        self._ssh = ssh

    async def setup(self, username: str = "coder") -> WorkerUserInfo:
        """Create OS user, copy config/SSH keys, verify agents.

        Agents are installed directly as the worker user (via
        ``AgentInstallService.install_agent(as_user=...)``) rather than
        installed on root and copied.  This method only creates the user
        and copies config/credentials needed before the install step.
        """
        safe_user = shlex.quote(username)
        home = f"/home/{username}"

        # Create user idempotently
        create_cmd = f"id -u {safe_user} &>/dev/null || useradd -m -s /bin/bash {safe_user}"
        _, stderr, rc = await self._ssh.run_command(create_cmd, timeout=15)
        if rc != 0:
            return WorkerUserInfo(
                exists=False,
                username=username,
                agents=[],
                error=f"Failed to create user: {stderr.strip()}",
            )

        # Prepare user directories and copy config/credentials
        setup_cmds = [
            f"mkdir -p {home}/.local/bin",
            # Copy Claude config + API keys (merge, don't destroy session data)
            f"cp -fL /root/.claude.json {home}/.claude.json 2>/dev/null || true",
            f"mkdir -p {home}/.claude",
            f"cp -rnL /root/.claude/* {home}/.claude/ 2>/dev/null || true",
            # Copy SSH keys so worker user has same git provider access as root
            f"mkdir -p {home}/.ssh && chmod 700 {home}/.ssh",
            f"cp -fL /root/.ssh/id_ed25519 {home}/.ssh/id_ed25519 2>/dev/null || true",
            f"cp -fL /root/.ssh/id_ed25519.pub {home}/.ssh/id_ed25519.pub 2>/dev/null || true",
            f"cp -fL /root/.ssh/id_rsa {home}/.ssh/id_rsa 2>/dev/null || true",
            f"cp -fL /root/.ssh/id_rsa.pub {home}/.ssh/id_rsa.pub 2>/dev/null || true",
            (
                f"test -f /root/.ssh/known_hosts && "
                f"cp -fL /root/.ssh/known_hosts {home}/.ssh/known_hosts 2>/dev/null || true"
            ),
            # Copy root's SSH config if present (may have ProxyCommand, etc.)
            f"cp -fL /root/.ssh/config {home}/.ssh/config 2>/dev/null || true",
            f"chmod 600 {home}/.ssh/id_* 2>/dev/null || true",
            f"chmod 600 {home}/.ssh/config 2>/dev/null || true",
            # Set up basic git config for the worker user
            (
                f'runuser -u {safe_user} -- git config --global user.name "autodev" 2>/dev/null || true'
            ),
            (
                f'runuser -u {safe_user} -- git config --global user.email "autodev@localhost" 2>/dev/null || true'
            ),
            # Persist PATH in .bashrc for interactive shells
            (
                f"grep -q '.local/bin' {home}/.bashrc 2>/dev/null || "
                f"echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> {home}/.bashrc"
            ),
        ]

        # Write platform env vars (tokens, API URLs) for agent plugins
        env_lines = self._build_env_vars()
        if env_lines:
            env_content = "\\n".join(env_lines)
            setup_cmds.extend(
                [
                    f'printf "{env_content}\\n" > {home}/.autodev_env',
                    f"chmod 600 {home}/.autodev_env",
                    (
                        f"grep -q 'autodev_env' {home}/.bashrc 2>/dev/null || "
                        f"echo '[ -f ~/.autodev_env ] && . ~/.autodev_env' >> {home}/.bashrc"
                    ),
                ]
            )

        # Set up git credential store with all configured provider tokens
        cred_lines = self._build_git_credentials()
        if cred_lines:
            cred_content = "\\n".join(cred_lines)
            setup_cmds.extend(
                [
                    f'printf "{cred_content}\\n" > {home}/.git-credentials',
                    f"chmod 600 {home}/.git-credentials",
                    f"runuser -u {safe_user} -- git config --global credential.helper store 2>/dev/null || true",
                ]
            )

        setup_cmds.append(f"chown -R {safe_user}:{safe_user} {home}")

        setup_script = " && ".join(setup_cmds)
        _, stderr, rc = await self._ssh.run_command(setup_script, timeout=60)
        if rc != 0:
            return WorkerUserInfo(
                exists=True,
                username=username,
                agents=[],
                error=f"Failed to set up user environment: {stderr.strip()}",
            )

        agents = await self._check_worker_agents(username)
        return WorkerUserInfo(exists=True, username=username, agents=agents)

    async def check_status(self, username: str = "coder") -> WorkerUserInfo:
        """Check if user exists and has binaries."""
        safe_user = shlex.quote(username)
        _, _, rc = await self._ssh.run_command(f"id -u {safe_user}", timeout=10)
        if rc != 0:
            return WorkerUserInfo(exists=False, username=username, agents=[])
        agents = await self._check_worker_agents(username)
        return WorkerUserInfo(exists=True, username=username, agents=agents)

    async def set_password(self, username: str, password: str) -> WorkerUserInfo:
        """Set the OS password for an existing worker user via chpasswd."""
        safe_user = shlex.quote(username)
        safe_pass = shlex.quote(password)
        cmd = f"echo {safe_user}:{safe_pass} | chpasswd"
        _, stderr, rc = await self._ssh.run_command(cmd, timeout=15)
        if rc != 0:
            return WorkerUserInfo(
                exists=True,
                username=username,
                agents=[],
                error=f"Failed to set password: {stderr.strip()}",
            )
        return WorkerUserInfo(exists=True, username=username, agents=[])

    async def sync_agents(self, username: str = "coder") -> WorkerUserInfo:
        """Re-sync config/credentials and check agent availability."""
        return await self.setup(username)

    @staticmethod
    def _build_env_vars() -> list[str]:
        """Build environment variable exports for the worker user.

        These are written to ~/.autodev_env and sourced from .bashrc so that
        agent plugins (github MCP, etc.) and CLI tools have access to tokens.
        """
        lines: list[str] = []

        if settings.github_token:
            lines.append(
                f"export GITHUB_PERSONAL_ACCESS_TOKEN={shlex.quote(settings.github_token)}"
            )
            lines.append(f"export GITHUB_TOKEN={shlex.quote(settings.github_token)}")

        if settings.gitea_token:
            lines.append(f"export GITEA_TOKEN={shlex.quote(settings.gitea_token)}")

        if settings.gitlab_token:
            lines.append(f"export GITLAB_TOKEN={shlex.quote(settings.gitlab_token)}")

        if settings.bitbucket_access_token:
            lines.append(
                f"export BITBUCKET_ACCESS_TOKEN={shlex.quote(settings.bitbucket_access_token)}"
            )

        return lines

    @staticmethod
    def _build_git_credentials() -> list[str]:
        """Build git-credentials lines from configured provider tokens."""
        lines: list[str] = []

        if settings.github_token:
            lines.append(f"https://x-access-token:{settings.github_token}@github.com")

        if settings.gitea_token and settings.gitea_url:
            parsed = urlparse(settings.gitea_url)
            host = parsed.hostname or "gitea.local"
            port_part = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
            scheme = parsed.scheme or "https"
            lines.append(f"{scheme}://ai-agent:{settings.gitea_token}@{host}{port_part}")

        if settings.gitlab_token and settings.gitlab_api_url:
            parsed = urlparse(settings.gitlab_api_url)
            host = parsed.hostname or "gitlab.com"
            lines.append(f"https://oauth2:{settings.gitlab_token}@{host}")

        if settings.bitbucket_access_token:
            lines.append(f"https://x-token-auth:{settings.bitbucket_access_token}@bitbucket.org")

        return lines

    async def _check_worker_agents(self, username: str) -> list[str]:
        """Discover which CLI agents the worker user can run."""
        home = f"/home/{username}"
        user_path = (
            f"{home}/.local/bin:{home}/.claude/bin:{home}/.claude/local/bin"
            ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        )
        safe_user = shlex.quote(username)
        found: list[str] = []
        for agent in _CLI_AGENTS:
            cmd = f"runuser -u {safe_user} -- bash -c 'export PATH={shlex.quote(user_path)} && command -v {agent}'"
            _, _, rc = await self._ssh.run_command(cmd, timeout=10)
            if rc == 0:
                found.append(agent)
        return found
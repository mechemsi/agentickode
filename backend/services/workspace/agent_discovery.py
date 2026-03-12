# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Discover available coding agents on a remote workspace server."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.services.workspace.ssh_service import SSHService

CLI_AGENTS = ["claude", "codex", "opencode", "aider", "gemini", "kimi"]

API_AGENTS = {
    "openhands": {"check": "curl -sf http://localhost:3000/api/health", "port": 3000},
}


@dataclass
class AgentInfo:
    agent_name: str
    agent_type: str  # cli_binary | api_service
    available: bool = True
    path: str | None = None
    version: str | None = None
    metadata: dict | None = field(default_factory=dict)


class AgentDiscoveryService:
    """Discover coding agents installed on a remote server via SSH."""

    def __init__(self, ssh: SSHService):
        self._ssh = ssh

    async def discover_all(self, as_user: str | None = None) -> list[AgentInfo]:
        """Discover agents. If as_user is set, run checks as that user via runuser."""
        agents: list[AgentInfo] = []
        for name in CLI_AGENTS:
            agent = await self._check_cli_agent(name, as_user)
            if agent:
                agents.append(agent)
        for name, cfg in API_AGENTS.items():
            agent = await self._check_api_agent(name, cfg["check"])
            if agent:
                agents.append(agent)
        return agents

    async def _run(self, cmd: str, as_user: str | None, timeout: int = 10):
        if as_user:
            return await self._ssh.run_command_as(as_user, cmd, timeout=timeout)
        return await self._ssh.run_command(cmd, timeout=timeout)

    async def _check_cli_agent(self, name: str, as_user: str | None = None) -> AgentInfo | None:
        stdout, _, exit_code = await self._run(f"command -v {name}", as_user)
        if exit_code != 0:
            return None

        path = stdout.strip()
        version = await self._get_version(name, as_user)
        return AgentInfo(
            agent_name=name,
            agent_type="cli_binary",
            path=path,
            version=version,
        )

    async def _get_version(self, name: str, as_user: str | None = None) -> str | None:
        stdout, _, exit_code = await self._run(
            f"{name} --version 2>/dev/null || {name} -V 2>/dev/null",
            as_user,
        )
        if exit_code == 0 and stdout.strip():
            return stdout.strip().split("\n")[0][:100]
        return None

    async def _check_api_agent(self, name: str, check_cmd: str) -> AgentInfo | None:
        _, _, exit_code = await self._ssh.run_command(check_cmd, timeout=10)
        if exit_code != 0:
            return None
        return AgentInfo(
            agent_name=name,
            agent_type="api_service",
        )
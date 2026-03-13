# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for AgentDiscoveryService."""

from unittest.mock import AsyncMock

import pytest

from backend.services.workspace.agent_discovery import AgentDiscoveryService


@pytest.fixture
def mock_ssh():
    return AsyncMock()


class TestDiscoverAll:
    async def test_finds_cli_and_api_agents(self, mock_ssh: AsyncMock):
        # claude found, aider found, codex not found, opencode not found, openhands found
        async def run_command(cmd: str, timeout: int = 30):
            if cmd == "command -v claude":
                return ("/usr/local/bin/claude\n", "", 0)
            if cmd == "command -v aider":
                return ("/usr/bin/aider\n", "", 0)
            if cmd.startswith("command -v codex") or cmd.startswith("command -v opencode"):
                return ("", "", 1)
            if cmd.startswith("claude --version"):
                return ("claude 1.0.0\n", "", 0)
            if cmd.startswith("aider --version"):
                return ("aider 0.50.1\n", "", 0)
            if cmd.startswith("curl -sf http://localhost:3000"):
                return ("", "", 0)
            return ("", "", 0)

        mock_ssh.run_command = AsyncMock(side_effect=run_command)

        svc = AgentDiscoveryService(mock_ssh)
        agents = await svc.discover_all()

        names = [a.agent_name for a in agents]
        assert "claude" in names
        assert "aider" in names
        assert "openhands" in names
        assert "codex" not in names
        assert "opencode" not in names

    async def test_no_agents_found(self, mock_ssh: AsyncMock):
        mock_ssh.run_command = AsyncMock(return_value=("", "", 1))
        svc = AgentDiscoveryService(mock_ssh)
        agents = await svc.discover_all()
        assert agents == []

    async def test_cli_agent_with_version(self, mock_ssh: AsyncMock):
        async def run_command(cmd: str, timeout: int = 30):
            if cmd == "command -v claude":
                return ("/usr/local/bin/claude\n", "", 0)
            if cmd.startswith("claude --version"):
                return ("claude 2.0.0\n", "", 0)
            return ("", "", 1)

        mock_ssh.run_command = AsyncMock(side_effect=run_command)
        svc = AgentDiscoveryService(mock_ssh)
        agents = await svc.discover_all()

        claude = next(a for a in agents if a.agent_name == "claude")
        assert claude.agent_type == "cli_binary"
        assert claude.path == "/usr/local/bin/claude"
        assert claude.version == "claude 2.0.0"

    async def test_cli_agent_version_fails(self, mock_ssh: AsyncMock):
        async def run_command(cmd: str, timeout: int = 30):
            if cmd == "command -v aider":
                return ("/usr/bin/aider\n", "", 0)
            return ("", "", 1)

        mock_ssh.run_command = AsyncMock(side_effect=run_command)
        svc = AgentDiscoveryService(mock_ssh)
        agents = await svc.discover_all()

        aider = next(a for a in agents if a.agent_name == "aider")
        assert aider.version is None

    async def test_openhands_api_check_fails(self, mock_ssh: AsyncMock):
        async def run_command(cmd: str, timeout: int = 30):
            if cmd.startswith("curl"):
                return ("", "Connection refused", 7)
            return ("", "", 1)

        mock_ssh.run_command = AsyncMock(side_effect=run_command)
        svc = AgentDiscoveryService(mock_ssh)
        agents = await svc.discover_all()
        assert not any(a.agent_name == "openhands" for a in agents)

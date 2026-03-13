# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for AgentInstallService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.agents import AgentSettings
from backend.seed import DEFAULT_AGENT_SETTINGS
from backend.services.workspace.agent_install_service import AgentInstallService


def _mock_setting(**overrides) -> MagicMock:
    """Create a mock AgentSettings with sensible defaults."""
    defaults = {
        "agent_name": "test-agent",
        "display_name": "Test Agent",
        "description": "A test agent",
        "agent_type": "cli_binary",
        "check_cmd": "command -v test-agent",
        "prereq_check": "command -v curl",
        "prereq_name": "curl",
        "install_cmd": "curl https://example.com/install.sh | bash",
        "post_install_cmd": "",
        "needs_non_root": False,
    }
    defaults.update(overrides)
    s = MagicMock(spec=AgentSettings)
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


def _all_seed_settings() -> list[MagicMock]:
    """Build mock AgentSettings list from seed data (same as a fresh DB)."""
    return [_mock_setting(**d) for d in DEFAULT_AGENT_SETTINGS]


class TestCheckAllAgents:
    @pytest.fixture
    def ssh_mock(self):
        return AsyncMock()

    async def test_returns_all_seeded_agents(self, ssh_mock):
        ssh_mock.run_command = AsyncMock(return_value=("", "", 1))
        svc = AgentInstallService(ssh_mock, agent_settings=_all_seed_settings())
        result = await svc.check_all_agents()
        assert len(result) == len(DEFAULT_AGENT_SETTINGS)
        names = {a.agent_name for a in result}
        expected = {d["agent_name"] for d in DEFAULT_AGENT_SETTINGS}
        assert names == expected

    async def test_marks_installed_agents(self, ssh_mock):
        async def side_effect(cmd, **kwargs):
            if cmd == "command -v claude":
                return ("/usr/bin/claude", "", 0)
            if "claude --version" in cmd:
                return ("claude 1.2.3", "", 0)
            return ("", "", 1)

        ssh_mock.run_command = AsyncMock(side_effect=side_effect)
        svc = AgentInstallService(ssh_mock, agent_settings=_all_seed_settings())
        result = await svc.check_all_agents()

        claude = next(a for a in result if a.agent_name == "claude")
        assert claude.installed is True
        assert claude.version == "claude 1.2.3"
        assert claude.path == "/usr/bin/claude"

        aider = next(a for a in result if a.agent_name == "aider")
        assert aider.installed is False
        assert aider.version is None

    async def test_all_agents_have_metadata(self, ssh_mock):
        ssh_mock.run_command = AsyncMock(return_value=("", "", 1))
        svc = AgentInstallService(ssh_mock, agent_settings=_all_seed_settings())
        result = await svc.check_all_agents()

        for agent in result:
            assert agent.display_name
            assert agent.description
            assert agent.agent_type in ("cli_binary", "api_service")

    async def test_empty_settings_returns_no_agents(self, ssh_mock):
        """With empty settings list, service has no agents to check."""
        ssh_mock.run_command = AsyncMock(return_value=("", "", 1))
        svc = AgentInstallService(ssh_mock, agent_settings=[])
        result = await svc.check_all_agents()
        assert result == []

    async def test_custom_agent_from_db(self, ssh_mock):
        """DB settings can define agents not in the default seed."""
        ssh_mock.run_command = AsyncMock(return_value=("", "", 1))
        custom = _mock_setting(
            agent_name="custom-agent",
            display_name="Custom Agent",
            description="A user-defined agent",
        )
        svc = AgentInstallService(ssh_mock, agent_settings=[custom])
        result = await svc.check_all_agents()
        assert len(result) == 1
        assert result[0].agent_name == "custom-agent"
        assert result[0].display_name == "Custom Agent"


class TestInstallAgent:
    @pytest.fixture
    def ssh_mock(self):
        return AsyncMock()

    @pytest.fixture
    def claude_settings(self):
        return [
            _mock_setting(
                agent_name="claude",
                display_name="Claude Code",
                description="Anthropic's AI coding agent",
                check_cmd="command -v claude",
                prereq_check="command -v curl",
                prereq_name="curl",
                install_cmd="curl -fsSL https://claude.ai/install.sh | bash",
                needs_non_root=True,
            )
        ]

    async def test_unknown_agent_returns_error(self, ssh_mock, claude_settings):
        svc = AgentInstallService(ssh_mock, agent_settings=claude_settings)
        result = await svc.install_agent("nonexistent")
        assert result.success is False
        assert "Unknown agent" in (result.error or "")

    async def test_prereq_failure(self, ssh_mock, claude_settings):
        ssh_mock.run_command = AsyncMock(return_value=("", "", 1))
        svc = AgentInstallService(ssh_mock, agent_settings=claude_settings)
        result = await svc.install_agent("claude")
        assert result.success is False
        assert "Prerequisite" in (result.error or "")

    async def test_install_success(self, ssh_mock, claude_settings):
        call_count = 0

        async def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("", "", 0)  # prereq check OK
            if call_count == 2:
                return ("installed", "", 0)  # install OK
            return ("/usr/bin/claude", "", 0)  # verify OK

        ssh_mock.run_command = AsyncMock(side_effect=side_effect)
        svc = AgentInstallService(ssh_mock, agent_settings=claude_settings)
        result = await svc.install_agent("claude")
        assert result.success is True
        assert result.agent_name == "claude"
        assert result.message is not None

    async def test_install_command_fails(self, ssh_mock, claude_settings):
        call_count = 0

        async def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("", "", 0)  # prereq OK
            return ("", "curl: (22) HTTP error 404", 1)  # install fails

        ssh_mock.run_command = AsyncMock(side_effect=side_effect)
        svc = AgentInstallService(ssh_mock, agent_settings=claude_settings)
        result = await svc.install_agent("claude")
        assert result.success is False
        assert "curl" in (result.error or "")

    async def test_install_succeeds_but_verify_fails(self, ssh_mock, claude_settings):
        call_count = 0

        async def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("", "", 0)  # prereq OK
            if call_count == 2:
                return ("", "", 0)  # install OK
            return ("", "", 1)  # verify fails

        ssh_mock.run_command = AsyncMock(side_effect=side_effect)
        svc = AgentInstallService(ssh_mock, agent_settings=claude_settings)
        result = await svc.install_agent("claude")
        assert result.success is False
        assert "not found after install" in (result.error or "")

    async def test_no_install_cmd_returns_error(self, ssh_mock):
        """Agent with empty install_cmd should return error."""
        settings = [
            _mock_setting(
                agent_name="no-install",
                display_name="No Install",
                description="Agent with no install command",
                install_cmd="",
                prereq_check="",
            )
        ]
        svc = AgentInstallService(ssh_mock, agent_settings=settings)
        result = await svc.install_agent("no-install")
        assert result.success is False
        assert "No install command" in (result.error or "")


class TestInstallAgentAsUser:
    @pytest.fixture
    def ssh_mock(self):
        return AsyncMock()

    @pytest.fixture
    def aider_settings(self):
        return [
            _mock_setting(
                agent_name="aider",
                display_name="Aider",
                description="Aider AI pair programming",
                check_cmd="command -v aider",
                prereq_check="command -v curl",
                prereq_name="curl",
                install_cmd="curl -fsSL https://aider.chat/install.sh | sh",
                needs_non_root=True,
            )
        ]

    async def test_install_as_user_wraps_commands(self, ssh_mock, aider_settings):
        """When as_user is set, agent commands should be wrapped with runuser."""
        ssh_mock.run_command = AsyncMock(return_value=("", "", 0))
        svc = AgentInstallService(ssh_mock, agent_settings=aider_settings)
        result = await svc.install_agent("aider", as_user="coder")
        assert result.success is True
        # prereq + cred_sync_before + install + cred_sync_after + verify = 5 calls
        assert ssh_mock.run_command.call_count == 5
        # Agent commands (prereq, install, verify) must use runuser
        for call in ssh_mock.run_command.call_args_list:
            cmd = call[0][0]
            # Credential sync runs as root (copies from /root/) — skip
            if "cp -fL /root/.claude.json" in cmd:
                continue
            assert "runuser" in cmd, f"Expected runuser in command: {cmd}"

    async def test_install_without_as_user_no_wrap(self, ssh_mock, aider_settings):
        """Without as_user, commands run directly (no runuser)."""
        ssh_mock.run_command = AsyncMock(return_value=("", "", 0))
        svc = AgentInstallService(ssh_mock, agent_settings=aider_settings)
        result = await svc.install_agent("aider")
        assert result.success is True
        # Verify no runuser in any call
        for call in ssh_mock.run_command.call_args_list:
            assert "runuser" not in call[0][0]


class TestSeedDataCompleteness:
    """Verify the seed data in DEFAULT_AGENT_SETTINGS covers all expected agents."""

    def test_seed_has_eight_agents(self):
        assert len(DEFAULT_AGENT_SETTINGS) == 8

    def test_seed_agent_names(self):
        names = {d["agent_name"] for d in DEFAULT_AGENT_SETTINGS}
        assert names == {
            "claude",
            "codex",
            "opencode",
            "aider",
            "gemini",
            "kimi",
            "copilot",
            "openhands",
        }

    def test_seed_entries_have_install_fields(self):
        for d in DEFAULT_AGENT_SETTINGS:
            assert d.get("check_cmd"), f"{d['agent_name']} missing check_cmd"
            assert d.get("agent_type"), f"{d['agent_name']} missing agent_type"
            assert d.get("install_cmd"), f"{d['agent_name']} missing install_cmd"

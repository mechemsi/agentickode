# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for ensure_agent_ready() auto-install helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.adapters.cli_adapter import CLIAdapter
from backend.services.adapters.ollama_adapter import OllamaAdapter
from backend.services.workspace.agent_install_service import InstallResult
from backend.services.workspace.worker_user_service import WorkerUserInfo
from backend.worker.phases._helpers import ensure_agent_ready


@pytest.fixture
def mock_ssh():
    ssh = AsyncMock()
    ssh.hostname = "10.0.0.1"
    ssh.port = 22
    ssh.username = "root"
    return ssh


@pytest.fixture
def mock_log():
    return AsyncMock()


@pytest.fixture
def claude_settings():
    """Mock AgentSettings for claude (needs_non_root=True)."""
    s = MagicMock()
    s.agent_name = "claude"
    s.check_cmd = "command -v claude"
    s.needs_non_root = True
    return s


class TestEnsureAgentReadySkipsNonCLI:
    async def test_skips_ollama_adapter(self, mock_log):
        svc = AsyncMock()
        adapter = OllamaAdapter(svc, "model-x")
        await ensure_agent_ready(adapter, log_fn=mock_log)
        mock_log.assert_not_called()


class TestEnsureAgentReadyAlreadyInstalled:
    async def test_agent_available_non_root_ssh_user(self, mock_log):
        """Agent available, SSH user is not root — just check, no worker user."""
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.username = "coder"  # not root
        ssh.run_command.return_value = ("", "", 0)  # agent check passes

        settings = MagicMock()
        settings.check_cmd = "command -v aider"
        settings.needs_non_root = False

        adapter = CLIAdapter(ssh, "aider")
        await ensure_agent_ready(adapter, log_fn=mock_log, agent_settings=settings)
        ssh.run_command.assert_called_once()

    async def test_agent_already_on_worker_user(self, mock_ssh, mock_log, claude_settings):
        """Worker user exists and already has the agent — no install needed."""
        adapter = CLIAdapter(mock_ssh, "claude")

        with patch("backend.worker.phases._helpers.WorkerUserService") as mock_user_svc_cls:
            mock_user_svc = AsyncMock()
            mock_user_svc.setup.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=["claude"]
            )
            mock_user_svc_cls.return_value = mock_user_svc

            await ensure_agent_ready(adapter, log_fn=mock_log, agent_settings=claude_settings)

            mock_user_svc.setup.assert_called_once_with("coder")
            assert adapter.worker_user == "coder"


class TestEnsureAgentReadyInstallOnWorkerUser:
    async def test_installs_on_worker_user_when_missing(self, mock_ssh, mock_log, claude_settings):
        """Agent not found for worker user — installs directly as worker user."""
        adapter = CLIAdapter(mock_ssh, "claude")

        with (
            patch("backend.worker.phases._helpers.AgentInstallService") as mock_install_cls,
            patch("backend.worker.phases._helpers.WorkerUserService") as mock_user_svc_cls,
        ):
            mock_install = AsyncMock()
            mock_install.install_agent.return_value = InstallResult(
                success=True, agent_name="claude", message="Installed"
            )
            mock_install_cls.return_value = mock_install

            mock_user_svc = AsyncMock()
            # First setup: agent NOT found
            mock_user_svc.setup.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=[]
            )
            # After install + check_status: agent found
            mock_user_svc.check_status.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=["claude"]
            )
            mock_user_svc_cls.return_value = mock_user_svc

            await ensure_agent_ready(adapter, log_fn=mock_log, agent_settings=claude_settings)

            # Should install as worker user, not root
            mock_install.install_agent.assert_called_once_with("claude", as_user="coder")
            assert adapter.worker_user == "coder"

    async def test_install_failure_raises(self, mock_ssh, mock_log, claude_settings):
        """Install as worker user fails — raises RuntimeError."""
        adapter = CLIAdapter(mock_ssh, "claude")

        with (
            patch("backend.worker.phases._helpers.AgentInstallService") as mock_install_cls,
            patch("backend.worker.phases._helpers.WorkerUserService") as mock_user_svc_cls,
        ):
            mock_install = AsyncMock()
            mock_install.install_agent.return_value = InstallResult(
                success=False, agent_name="claude", error="curl failed"
            )
            mock_install_cls.return_value = mock_install

            mock_user_svc = AsyncMock()
            mock_user_svc.setup.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=[]
            )
            mock_user_svc_cls.return_value = mock_user_svc

            with pytest.raises(RuntimeError, match="Install of claude.*failed"):
                await ensure_agent_ready(adapter, log_fn=mock_log, agent_settings=claude_settings)

    async def test_worker_user_creation_failure_raises(self, mock_ssh, mock_log, claude_settings):
        """Worker user creation fails — raises RuntimeError."""
        adapter = CLIAdapter(mock_ssh, "claude")

        with patch("backend.worker.phases._helpers.WorkerUserService") as mock_user_svc_cls:
            mock_user_svc = AsyncMock()
            mock_user_svc.setup.return_value = WorkerUserInfo(
                exists=False, username="coder", agents=[], error="useradd failed"
            )
            mock_user_svc_cls.return_value = mock_user_svc

            with pytest.raises(RuntimeError, match="Failed to create worker user"):
                await ensure_agent_ready(adapter, log_fn=mock_log, agent_settings=claude_settings)

    async def test_raises_when_still_missing_after_install(
        self, mock_ssh, mock_log, claude_settings
    ):
        """Install succeeds but check_status still doesn't find agent — raises."""
        adapter = CLIAdapter(mock_ssh, "claude")

        with (
            patch("backend.worker.phases._helpers.AgentInstallService") as mock_install_cls,
            patch("backend.worker.phases._helpers.WorkerUserService") as mock_user_svc_cls,
        ):
            mock_install = AsyncMock()
            mock_install.install_agent.return_value = InstallResult(
                success=True, agent_name="claude", message="Installed"
            )
            mock_install_cls.return_value = mock_install

            mock_user_svc = AsyncMock()
            mock_user_svc.setup.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=[]
            )
            mock_user_svc.check_status.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=[]
            )
            mock_user_svc_cls.return_value = mock_user_svc

            with pytest.raises(RuntimeError, match="still not available"):
                await ensure_agent_ready(adapter, log_fn=mock_log, agent_settings=claude_settings)


class TestEnsureAgentReadyAllAgentsNonRoot:
    async def test_all_cli_agents_default_to_non_root(self, mock_ssh, mock_log):
        """Without DB settings, all CLI agents default to needs_non_root=True."""
        adapter = CLIAdapter(mock_ssh, "aider")

        with patch("backend.worker.phases._helpers.WorkerUserService") as mock_user_svc_cls:
            mock_user_svc = AsyncMock()
            mock_user_svc.setup.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=["aider"]
            )
            mock_user_svc_cls.return_value = mock_user_svc

            await ensure_agent_ready(adapter, log_fn=mock_log)

            mock_user_svc.setup.assert_called_once_with("coder")
            assert adapter.worker_user == "coder"


class TestEnsureAgentReadyWithDBSettings:
    """Test DB-driven agent_settings parameter."""

    async def test_uses_db_check_cmd_non_root_ssh(self, mock_log):
        """When agent_settings with needs_non_root=False and non-root SSH user."""
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.username = "coder"  # not root
        ssh.run_command.return_value = ("", "", 0)
        adapter = CLIAdapter(ssh, "aider")

        settings = MagicMock()
        settings.check_cmd = "custom-check-aider"
        settings.needs_non_root = False

        await ensure_agent_ready(adapter, log_fn=mock_log, agent_settings=settings)

        ssh.run_command.assert_called_once_with("custom-check-aider", timeout=10)

    async def test_uses_db_needs_non_root(self, mock_ssh, mock_log):
        """When agent_settings.needs_non_root=True, creates worker user."""
        adapter = CLIAdapter(mock_ssh, "aider")

        settings = MagicMock()
        settings.check_cmd = "command -v aider"
        settings.needs_non_root = True

        with patch("backend.worker.phases._helpers.WorkerUserService") as mock_user_svc_cls:
            mock_user_svc = AsyncMock()
            mock_user_svc.setup.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=["aider"]
            )
            mock_user_svc_cls.return_value = mock_user_svc

            await ensure_agent_ready(adapter, log_fn=mock_log, agent_settings=settings)

            mock_user_svc.setup.assert_called_once_with("coder")

    async def test_no_log_fn_uses_default(self, mock_ssh):
        """Passing no log_fn should not crash."""
        adapter = CLIAdapter(mock_ssh, "aider")

        with patch("backend.worker.phases._helpers.WorkerUserService") as mock_user_svc_cls:
            mock_user_svc = AsyncMock()
            mock_user_svc.setup.return_value = WorkerUserInfo(
                exists=True, username="coder", agents=["aider"]
            )
            mock_user_svc_cls.return_value = mock_user_svc

            await ensure_agent_ready(adapter, log_fn=None)

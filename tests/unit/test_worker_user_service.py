# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for WorkerUserService."""

from unittest.mock import AsyncMock

from backend.services.workspace.worker_user_service import WorkerUserService


class TestSetup:
    async def test_setup_creates_user_and_copies_config(self):
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("", "", 0),  # create user
            ("", "", 0),  # setup config/credentials
            # _check_worker_agents: one agent found
            ("", "", 1),  # claude not found
            ("", "", 1),  # codex not found
            ("/usr/bin/aider", "", 0),  # aider found
            ("", "", 1),  # opencode not found
            ("", "", 1),  # gemini not found
            ("", "", 1),  # kimi not found
            ("", "", 1),  # copilot not found
        ]
        svc = WorkerUserService(ssh)
        info = await svc.setup("coder")

        assert info.exists is True
        assert info.username == "coder"
        assert info.agents == ["aider"]
        assert info.error is None

    async def test_setup_user_creation_fails(self):
        ssh = AsyncMock()
        ssh.run_command.return_value = ("", "useradd: error", 1)
        svc = WorkerUserService(ssh)
        info = await svc.setup("coder")

        assert info.exists is False
        assert info.error is not None
        assert "Failed to create user" in info.error

    async def test_setup_config_copy_fails(self):
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("", "", 0),  # create user OK
            ("", "permission denied", 1),  # config copy fails
        ]
        svc = WorkerUserService(ssh)
        info = await svc.setup("coder")

        assert info.exists is True
        assert info.error is not None
        assert "Failed to set up user environment" in info.error


class TestCheckStatus:
    async def test_user_exists(self):
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("1000", "", 0),  # id -u coder
            # _check_worker_agents
            ("/home/coder/.local/bin/claude", "", 0),  # claude found
            ("", "", 1),  # codex
            ("", "", 1),  # aider
            ("", "", 1),  # opencode
            ("", "", 1),  # gemini
            ("", "", 1),  # kimi
            ("", "", 1),  # copilot
        ]
        svc = WorkerUserService(ssh)
        info = await svc.check_status("coder")

        assert info.exists is True
        assert info.agents == ["claude"]

    async def test_user_not_exists(self):
        ssh = AsyncMock()
        ssh.run_command.return_value = ("", "no such user", 1)
        svc = WorkerUserService(ssh)
        info = await svc.check_status("coder")

        assert info.exists is False
        assert info.agents == []


class TestSetPassword:
    async def test_set_password_success(self):
        ssh = AsyncMock()
        ssh.run_command.return_value = ("", "", 0)
        svc = WorkerUserService(ssh)
        info = await svc.set_password("coder", "s3cret")

        assert info.exists is True
        assert info.username == "coder"
        assert info.error is None
        # Verify chpasswd command was called
        call_args = ssh.run_command.call_args[0][0]
        assert "chpasswd" in call_args

    async def test_set_password_failure(self):
        ssh = AsyncMock()
        ssh.run_command.return_value = ("", "chpasswd: error", 1)
        svc = WorkerUserService(ssh)
        info = await svc.set_password("coder", "s3cret")

        assert info.exists is True
        assert info.error is not None
        assert "Failed to set password" in info.error


class TestSyncAgents:
    async def test_sync_calls_setup(self):
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("", "", 0),  # create user
            ("", "", 0),  # setup config
            # _check_worker_agents
            ("", "", 1),
            ("", "", 1),
            ("", "", 1),
            ("", "", 1),
            ("", "", 1),
            ("", "", 1),
            ("", "", 1),
        ]
        svc = WorkerUserService(ssh)
        info = await svc.sync_agents("coder")
        assert info.exists is True
        assert info.agents == []

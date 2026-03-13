# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for RemoteSandbox service."""

from unittest.mock import AsyncMock

import pytest

from backend.services.workspace.sandbox import RemoteSandbox, RemoteSandboxError


@pytest.fixture()
def mock_ssh():
    ssh = AsyncMock()
    ssh.hostname = "10.10.50.25"
    return ssh


@pytest.fixture()
def remote_sandbox(mock_ssh):
    return RemoteSandbox(mock_ssh, templates_path="/opt/agentickode/docker/sandboxes")


class TestStartSandbox:
    async def test_template_not_found(self, remote_sandbox, mock_ssh):
        mock_ssh.run_command.return_value = ("", "", 1)  # test -d fails
        ok, url = await remote_sandbox.start_sandbox(
            "/workspaces/proj", template="nonexistent", task_id="t1"
        )
        assert ok is False
        assert url is None

    async def test_successful_start(self, remote_sandbox, mock_ssh):
        mock_ssh.run_command.side_effect = [
            ("", "", 0),  # test -d template
            ("", "", 0),  # mkdir + cp
            ("", "", 0),  # printf .env
            ("", "", 0),  # docker compose up
        ]
        ok, url = await remote_sandbox.start_sandbox(
            "/workspaces/proj", template="php", task_id="t1"
        )
        assert ok is True
        assert url == "http://10.10.50.25:8080"

    async def test_custom_port(self, remote_sandbox, mock_ssh):
        mock_ssh.run_command.side_effect = [
            ("", "", 0),  # test -d
            ("", "", 0),  # mkdir + cp
            ("", "", 0),  # printf .env
            ("", "", 0),  # docker compose up
        ]
        ok, url = await remote_sandbox.start_sandbox(
            "/workspaces/proj", template="php", task_id="t1", http_port=9090
        )
        assert url == "http://10.10.50.25:9090"

    async def test_copy_failure_raises(self, remote_sandbox, mock_ssh):
        mock_ssh.run_command.side_effect = [
            ("", "", 0),  # test -d template exists
            ("", "Permission denied", 1),  # cp fails
        ]
        with pytest.raises(RemoteSandboxError, match="Failed to copy"):
            await remote_sandbox.start_sandbox("/workspaces/proj", template="php", task_id="t1")

    async def test_docker_compose_failure(self, remote_sandbox, mock_ssh):
        mock_ssh.run_command.side_effect = [
            ("", "", 0),  # test -d
            ("", "", 0),  # mkdir + cp
            ("", "", 0),  # printf .env
            ("", "service not found", 1),  # docker compose up fails
        ]
        ok, url = await remote_sandbox.start_sandbox(
            "/workspaces/proj", template="php", task_id="t1"
        )
        assert ok is False
        assert url is None

    async def test_env_vars_included(self, remote_sandbox, mock_ssh):
        mock_ssh.run_command.side_effect = [
            ("", "", 0),  # test -d
            ("", "", 0),  # mkdir + cp
            ("", "", 0),  # printf .env
            ("", "", 0),  # docker compose up
        ]
        await remote_sandbox.start_sandbox(
            "/workspaces/proj",
            template="php",
            task_id="t1",
            env_vars={"DB_HOST": "localhost"},
        )
        env_cmd = mock_ssh.run_command.call_args_list[2][0][0]
        assert "DB_HOST=localhost" in env_cmd


class TestStopSandbox:
    async def test_stop_no_compose_file(self, remote_sandbox, mock_ssh):
        mock_ssh.run_command.return_value = ("", "", 1)  # test -f fails
        await remote_sandbox.stop_sandbox("/workspaces/proj")
        assert mock_ssh.run_command.call_count == 1

    async def test_stop_with_compose_file(self, remote_sandbox, mock_ssh):
        mock_ssh.run_command.side_effect = [
            ("", "", 0),  # test -f
            ("", "", 0),  # docker compose down
        ]
        await remote_sandbox.stop_sandbox("/workspaces/proj")
        down_cmd = mock_ssh.run_command.call_args_list[1][0][0]
        assert "docker compose down" in down_cmd

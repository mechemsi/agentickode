# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for role adapter implementations."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.adapters.cli_adapter import CLIAdapter
from backend.services.adapters.cli_wrappers import wrap_for_user
from backend.services.adapters.factory import AdapterFactory
from backend.services.adapters.ollama_adapter import OllamaAdapter
from backend.services.adapters.openhands_adapter import OpenHandsAdapter
from backend.services.adapters.protocol import RoleAdapter


class TestOllamaAdapter:
    def test_provider_name(self):
        svc = AsyncMock()
        adapter = OllamaAdapter(svc, "qwen2.5-coder:32b", server_name="gpu-01")
        assert adapter.provider_name == "ollama/qwen2.5-coder:32b@gpu-01"

    def test_provider_name_no_server(self):
        svc = AsyncMock()
        adapter = OllamaAdapter(svc, "model-x")
        assert adapter.provider_name == "ollama/model-x"

    async def test_generate(self):
        from backend.services.ollama_service import OllamaResult

        svc = AsyncMock()
        svc.generate.return_value = OllamaResult(
            text="response text", prompt_tokens=10, completion_tokens=20, total_duration_ns=100
        )
        adapter = OllamaAdapter(svc, "model-x")

        result = await adapter.generate("prompt", temperature=0.5, num_predict=1024)

        svc.generate.assert_called_once_with(
            "prompt", model="model-x", temperature=0.5, num_predict=1024
        )
        assert result == "response text"
        assert adapter.last_token_usage == (10, 20)

    async def test_run_task_raises(self):
        svc = AsyncMock()
        adapter = OllamaAdapter(svc, "model-x")
        with pytest.raises(NotImplementedError):
            await adapter.run_task("/ws", "do something")

    async def test_is_available(self):
        svc = AsyncMock()
        svc.is_healthy.return_value = True
        adapter = OllamaAdapter(svc, "model-x")
        assert await adapter.is_available() is True

    def test_implements_protocol(self):
        svc = AsyncMock()
        adapter = OllamaAdapter(svc, "model-x")
        assert isinstance(adapter, RoleAdapter)


class TestOpenHandsAdapter:
    def test_provider_name(self):
        svc = AsyncMock()
        adapter = OpenHandsAdapter(svc)
        assert adapter.provider_name == "agent/openhands"

    async def test_generate(self):
        svc = AsyncMock()
        svc.run_agent.return_value = {"output": "generated text"}
        adapter = OpenHandsAdapter(svc)

        result = await adapter.generate("prompt")
        assert result == "generated text"
        svc.run_agent.assert_called_once_with(
            workspace="/tmp", instruction="prompt", max_iterations=1
        )

    async def test_run_task(self):
        svc = AsyncMock()
        svc.run_agent.return_value = {"files_changed": ["a.py"]}
        adapter = OpenHandsAdapter(svc)

        result = await adapter.run_task("/ws", "do X", max_iterations=10)
        assert result == {"files_changed": ["a.py"]}
        svc.run_agent.assert_called_once_with(
            workspace="/ws", instruction="do X", max_iterations=10
        )

    async def test_is_available(self):
        svc = AsyncMock()
        svc.is_healthy.return_value = False
        adapter = OpenHandsAdapter(svc)
        assert await adapter.is_available() is False


class TestCLIAdapter:
    def test_unknown_agent_raises(self):
        ssh = AsyncMock()
        with pytest.raises(ValueError, match="Unknown CLI agent"):
            CLIAdapter(ssh, "unknown-agent")

    def test_provider_name(self):
        ssh = AsyncMock()
        adapter = CLIAdapter(ssh, "claude", server_name="ws-01")
        assert adapter.provider_name == "agent/claude@ws-01"

    async def test_generate(self):
        ssh = AsyncMock()
        # First call: write temp file
        ssh.run_command.side_effect = [
            ("/tmp/xyz\n", "", 0),  # write prompt file
            ("generated output", "", 0),  # agent run
            ("", "", 0),  # cleanup
        ]
        adapter = CLIAdapter(ssh, "claude")

        result = await adapter.generate("hello prompt")
        assert result == "generated output"
        assert ssh.run_command.call_count == 3

    async def test_run_task(self):
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.run_command.side_effect = [
            ("", "", 0),  # is_available check
            ("/tmp/inst\n", "", 0),  # write instruction file
            ("task output", "", 0),  # agent run
            ("", "", 0),  # cleanup
            ("a.py\nb.py\n", "", 0),  # git diff --name-only
        ]
        adapter = CLIAdapter(ssh, "aider")

        result = await adapter.run_task("/workspace", "fix the bug")
        assert result["output"] == "task output"
        assert result["exit_code"] == 0
        assert result["files_changed"] == ["a.py", "b.py"]
        assert ssh.run_command.call_count == 5

    async def test_run_task_agent_not_found(self):
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.run_command.return_value = ("", "not found", 1)
        adapter = CLIAdapter(ssh, "aider")

        result = await adapter.run_task("/workspace", "fix the bug")
        assert result["exit_code"] == 127

    async def test_is_available_true(self):
        ssh = AsyncMock()
        ssh.run_command.return_value = ("", "", 0)
        adapter = CLIAdapter(ssh, "codex")
        assert await adapter.is_available() is True

    async def test_is_available_false(self):
        ssh = AsyncMock()
        ssh.run_command.return_value = ("", "not found", 1)
        adapter = CLIAdapter(ssh, "codex")
        assert await adapter.is_available() is False

    async def test_run_task_with_worker_user(self):
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.username = "root"
        ssh.run_command.side_effect = [
            ("", "", 0),  # is_available check
            ("/tmp/inst\n", "", 0),  # write instruction file
            ("task output", "", 0),  # agent run
            ("", "", 0),  # cleanup
            ("a.py\n", "", 0),  # git diff
        ]
        adapter = CLIAdapter(ssh, "claude", worker_user="coder")
        result = await adapter.run_task("/workspace", "do work")
        assert result["output"] == "task output"
        # The agent-run command should use _wrap_for_user (no _ENSURE_CODER_USER)
        agent_cmd = ssh.run_command.call_args_list[2][0][0]
        assert "runuser -u coder" in agent_cmd
        # Should NOT contain useradd (that's the legacy path)
        assert "useradd" not in agent_cmd

    async def test_run_task_legacy_non_root(self):
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.username = "root"
        ssh.run_command.side_effect = [
            ("", "", 0),  # is_available check
            ("/tmp/inst\n", "", 0),  # write instruction file
            ("task output", "", 0),  # agent run
            ("", "", 0),  # cleanup
            ("a.py\n", "", 0),  # git diff
        ]
        adapter = CLIAdapter(ssh, "claude", needs_non_root=True)  # no worker_user
        result = await adapter.run_task("/workspace", "do work")
        assert result["output"] == "task output"
        # Legacy path should include useradd
        agent_cmd = ssh.run_command.call_args_list[2][0][0]
        assert "useradd" in agent_cmd
        assert "runuser -u coder" in agent_cmd

    def test_wrap_for_user(self):
        cmd = "cd /ws && cat /tmp/inst | claude --print"
        result = wrap_for_user(cmd, "/ws", "/tmp/inst", "coder")
        assert "chown -R coder:coder" in result
        assert "runuser -u coder" in result
        assert "/home/coder/.local/bin" in result
        # Should NOT contain useradd
        assert "useradd" not in result


class TestAdapterFactory:
    def test_create_ollama_adapter(self):
        client = MagicMock()
        openhands = AsyncMock()
        factory = AdapterFactory(http_client=client, openhands=openhands)

        server = MagicMock()
        server.url = "http://localhost:11434"
        server.name = "gpu-01"

        adapter = factory.create_ollama_adapter(server, "qwen:32b")
        assert isinstance(adapter, OllamaAdapter)
        assert adapter.provider_name == "ollama/qwen:32b@gpu-01"

    def test_create_agent_adapter_openhands(self):
        client = MagicMock()
        openhands = AsyncMock()
        factory = AdapterFactory(http_client=client, openhands=openhands)

        adapter = factory.create_agent_adapter("openhands")
        assert isinstance(adapter, OpenHandsAdapter)

    def test_create_agent_adapter_cli(self):
        client = MagicMock()
        openhands = AsyncMock()
        factory = AdapterFactory(http_client=client, openhands=openhands)

        ws = MagicMock()
        ws.hostname = "10.0.0.1"
        ws.port = 22
        ws.username = "root"
        ws.ssh_key_path = None
        ws.name = "ws-01"

        adapter = factory.create_agent_adapter("claude", workspace_server=ws)
        assert isinstance(adapter, CLIAdapter)

    def test_create_agent_adapter_cli_with_worker_user(self):
        client = MagicMock()
        openhands = AsyncMock()
        factory = AdapterFactory(http_client=client, openhands=openhands)

        ws = MagicMock()
        ws.hostname = "10.0.0.1"
        ws.port = 22
        ws.username = "root"
        ws.ssh_key_path = None
        ws.name = "ws-01"
        ws.worker_user = "coder"
        ws.worker_user_status = "ready"

        adapter = factory.create_agent_adapter("claude", workspace_server=ws)
        assert isinstance(adapter, CLIAdapter)
        assert adapter.worker_user == "coder"

    def test_create_agent_adapter_cli_worker_user_not_ready(self):
        client = MagicMock()
        openhands = AsyncMock()
        factory = AdapterFactory(http_client=client, openhands=openhands)

        ws = MagicMock()
        ws.hostname = "10.0.0.1"
        ws.port = 22
        ws.username = "root"
        ws.ssh_key_path = None
        ws.name = "ws-01"
        ws.worker_user = "coder"
        ws.worker_user_status = "error"

        adapter = factory.create_agent_adapter("claude", workspace_server=ws)
        assert isinstance(adapter, CLIAdapter)
        assert adapter.worker_user is None

    def test_create_cli_without_workspace_raises(self):
        client = MagicMock()
        openhands = AsyncMock()
        factory = AdapterFactory(http_client=client, openhands=openhands)

        with pytest.raises(ValueError, match="requires a workspace server"):
            factory.create_agent_adapter("claude")
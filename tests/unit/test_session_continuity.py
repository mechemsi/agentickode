# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for CLIAdapter session continuity feature."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.adapters.cli_adapter import CLIAdapter
from backend.services.adapters.cli_commands import AGENT_COMMANDS
from backend.services.role_resolver import ResolvedRole
from backend.worker.phases import planning


class TestSupportsSession:
    def test_claude_supports_session(self):
        ssh = AsyncMock()
        adapter = CLIAdapter(ssh, "claude")
        assert adapter.supports_session is True

    def test_codex_does_not_support_session(self):
        ssh = AsyncMock()
        adapter = CLIAdapter(ssh, "codex")
        assert adapter.supports_session is False

    def test_aider_does_not_support_session(self):
        ssh = AsyncMock()
        adapter = CLIAdapter(ssh, "aider")
        assert adapter.supports_session is False

    def test_opencode_does_not_support_session(self):
        ssh = AsyncMock()
        adapter = CLIAdapter(ssh, "opencode")
        assert adapter.supports_session is False

    def test_gemini_does_not_support_session(self):
        ssh = AsyncMock()
        adapter = CLIAdapter(ssh, "gemini")
        assert adapter.supports_session is False

    def test_kimi_does_not_support_session(self):
        ssh = AsyncMock()
        adapter = CLIAdapter(ssh, "kimi")
        assert adapter.supports_session is False


class TestAgentCommandStructure:
    def test_claude_has_task_continue_command(self):
        cmds = AGENT_COMMANDS["claude"]
        assert "task_continue" in cmds
        assert "{session_id}" in str(cmds["task_continue"])
        assert "--resume" in str(cmds["task_continue"])

    def test_claude_has_task_session_start_command(self):
        cmds = AGENT_COMMANDS["claude"]
        assert "task_session_start" in cmds
        assert "{session_id}" in str(cmds["task_session_start"])
        assert "--session-id" in str(cmds["task_session_start"])

    def test_claude_has_generate_session_start_command(self):
        cmds = AGENT_COMMANDS["claude"]
        assert "generate_session_start" in cmds
        template = str(cmds["generate_session_start"])
        assert "{session_id}" in template
        assert "--session-id" in template
        assert "{workspace}" in template

    def test_claude_generate_continue_needs_workspace(self):
        """generate_continue must cd to workspace for session lookup."""
        cmds = AGENT_COMMANDS["claude"]
        assert "generate_continue" in cmds
        template = str(cmds["generate_continue"])
        assert "{workspace}" in template
        assert "cd {workspace}" in template
        assert "--resume" in template

    def test_non_session_agents_no_task_continue(self):
        for agent in ["codex", "aider", "opencode", "gemini", "kimi"]:
            cmds = AGENT_COMMANDS[agent]
            assert "task_continue" not in cmds, f"{agent} should not have task_continue"

    def test_all_agents_have_required_keys(self):
        required = {"generate", "task", "check", "supports_session"}
        for agent, cmds in AGENT_COMMANDS.items():
            for key in required:
                assert key in cmds, f"{agent} missing key: {key}"


class TestRunTaskWithSession:
    async def test_run_task_without_session_uses_task_command(self):
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.run_command.side_effect = [
            ("", "", 0),  # is_available
            ("/tmp/inst\n", "", 0),  # write instruction
            ("output", "", 0),  # agent run
            ("", "", 0),  # cleanup
            ("a.py\n", "", 0),  # git diff
        ]
        adapter = CLIAdapter(ssh, "aider")

        result = await adapter.run_task("/workspace", "do work")
        assert result["exit_code"] == 0
        # No session_id passed, no session_id in result beyond None
        assert result.get("session_id") is None

        # Verify the aider task command was used (not task_continue)
        agent_cmd = ssh.run_command.call_args_list[2][0][0]
        assert "aider" in agent_cmd

    async def test_run_task_with_session_uses_continue_command_for_claude(self):
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.username = "user"  # non-root so no wrapping
        ssh.run_command.side_effect = [
            ("", "", 0),  # is_available
            ("/tmp/inst\n", "", 0),  # write instruction
            ("output", "", 0),  # agent run
            ("", "", 0),  # cleanup
            ("f.py\n", "", 0),  # git diff
        ]
        adapter = CLIAdapter(ssh, "claude")

        session_uuid = "abc123-def456-789"
        result = await adapter.run_task("/workspace", "do work", session_id=session_uuid)
        assert result["exit_code"] == 0
        # session_id should be passed through in result
        assert result["session_id"] == session_uuid

        # Verify --resume flag was included in the command (default: resume, not start)
        agent_cmd = ssh.run_command.call_args_list[2][0][0]
        assert "--resume" in agent_cmd
        assert session_uuid in agent_cmd

    async def test_run_task_new_session_uses_session_id_flag(self):
        """First subtask with new_session=True uses --session-id to CREATE the session."""
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.username = "user"
        ssh.run_command.side_effect = [
            ("", "", 0),  # is_available
            ("/tmp/inst\n", "", 0),  # write instruction
            ("output", "", 0),  # agent run
            ("", "", 0),  # cleanup
            ("f.py\n", "", 0),  # git diff
        ]
        adapter = CLIAdapter(ssh, "claude")

        session_uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = await adapter.run_task(
            "/workspace", "do work", session_id=session_uuid, new_session=True
        )
        assert result["exit_code"] == 0
        assert result["session_id"] == session_uuid

        # Verify --session-id flag was used (NOT --resume)
        agent_cmd = ssh.run_command.call_args_list[2][0][0]
        assert "--session-id" in agent_cmd
        assert "--resume" not in agent_cmd
        assert session_uuid in agent_cmd

    async def test_run_task_session_not_used_for_non_session_agent(self):
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.run_command.side_effect = [
            ("", "", 0),  # is_available
            ("/tmp/inst\n", "", 0),  # write instruction
            ("output", "", 0),  # agent run
            ("", "", 0),  # cleanup
            ("f.py\n", "", 0),  # git diff
        ]
        adapter = CLIAdapter(ssh, "codex")

        # Even if session_id is passed, codex doesn't support it
        result = await adapter.run_task("/workspace", "do work", session_id="some-id")
        assert result["exit_code"] == 0

        # Verify regular codex command was used (no --resume)
        agent_cmd = ssh.run_command.call_args_list[2][0][0]
        assert "--resume" not in agent_cmd

    async def test_run_task_returns_session_id_passthrough(self):
        """session_id in result equals the one passed in."""
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.username = "user"
        ssh.run_command.side_effect = [
            ("", "", 0),
            ("/tmp/inst\n", "", 0),
            ("output", "", 0),
            ("", "", 0),
            ("", "", 0),
        ]
        adapter = CLIAdapter(ssh, "claude")
        my_session = "test-session-id-123"

        result = await adapter.run_task("/ws", "instruction", session_id=my_session)
        assert result["session_id"] == my_session

    async def test_run_task_no_system_prompt_on_continuation(self):
        """When session_id is provided, system_prompt is NOT prepended to instruction."""
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.username = "user"
        ssh.run_command.side_effect = [
            ("", "", 0),
            ("/tmp/inst\n", "", 0),
            ("output", "", 0),
            ("", "", 0),
            ("", "", 0),
        ]
        adapter = CLIAdapter(ssh, "claude")

        await adapter.run_task(
            "/ws",
            "short instruction",
            system_prompt="SYSTEM PROMPT TEXT",
            session_id="existing-session",
        )

        # The write-instruction call should NOT include the system prompt text
        write_cmd = ssh.run_command.call_args_list[1][0][0]
        assert "SYSTEM PROMPT TEXT" not in write_cmd

    async def test_run_task_with_system_prompt_no_session(self):
        """Without session_id, system_prompt IS prepended."""
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.run_command.side_effect = [
            ("", "", 0),
            ("/tmp/inst\n", "", 0),
            ("output", "", 0),
            ("", "", 0),
            ("", "", 0),
        ]
        adapter = CLIAdapter(ssh, "aider")

        await adapter.run_task(
            "/ws",
            "short instruction",
            system_prompt="SYSTEM PROMPT TEXT",
        )

        # The write-instruction call SHOULD include the system prompt text
        write_cmd = ssh.run_command.call_args_list[1][0][0]
        assert "SYSTEM PROMPT TEXT" in write_cmd

    async def test_run_task_not_available_returns_none_session_id(self):
        """Agent not found — early return includes session_id: None."""
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.run_command.return_value = ("", "not found", 1)  # is_available fails
        adapter = CLIAdapter(ssh, "aider")

        result = await adapter.run_task("/ws", "instruction", session_id="some-id")
        assert result["exit_code"] == 127
        assert result["session_id"] is None


class TestGenerateWithSession:
    async def test_generate_without_session_uses_generate_command(self):
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("/tmp/prompt\n", "", 0),  # write prompt
            ("generated output", "", 0),  # agent run
            ("", "", 0),  # cleanup
        ]
        adapter = CLIAdapter(ssh, "claude")

        result = await adapter.generate("my prompt")
        assert result == "generated output"

        # Verify the generate command was used (cat ... | claude --print)
        gen_cmd = ssh.run_command.call_args_list[1][0][0]
        assert "--print" in gen_cmd
        assert "--resume" not in gen_cmd

    async def test_generate_with_session_uses_generate_continue_command(self):
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("/tmp/prompt\n", "", 0),  # write prompt
            ("generated output", "", 0),  # agent run
            ("", "", 0),  # cleanup
        ]
        adapter = CLIAdapter(ssh, "claude")

        result = await adapter.generate(
            "my prompt", session_id="my-session-abc", workspace="/workspace"
        )
        assert result == "generated output"

        # Verify --resume was included via generate_continue (not task_continue)
        gen_cmd = ssh.run_command.call_args_list[1][0][0]
        assert "--resume" in gen_cmd
        assert "my-session-abc" in gen_cmd
        # Should use generate_continue with cd to workspace for session lookup
        assert "--dangerously-skip-permissions" not in gen_cmd
        assert "cd /workspace" in gen_cmd

    async def test_generate_with_session_but_no_workspace_falls_back(self):
        """Without workspace, session_id alone can't use generate_continue."""
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("/tmp/prompt\n", "", 0),  # write prompt
            ("generated output", "", 0),  # agent run
            ("", "", 0),  # cleanup
        ]
        adapter = CLIAdapter(ssh, "claude")

        result = await adapter.generate("my prompt", session_id="my-session-abc")
        assert result == "generated output"

        # Without workspace, falls back to regular generate (no --resume)
        gen_cmd = ssh.run_command.call_args_list[1][0][0]
        assert "--resume" not in gen_cmd
        assert "--print" in gen_cmd

    async def test_generate_no_system_prompt_on_continuation(self):
        """System prompt not prepended when session_id is provided."""
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("/tmp/prompt\n", "", 0),
            ("output", "", 0),
            ("", "", 0),
        ]
        adapter = CLIAdapter(ssh, "claude")

        await adapter.generate(
            "instruction",
            system_prompt="SYS PROMPT",
            session_id="existing-session",
            workspace="/workspace",
        )

        write_cmd = ssh.run_command.call_args_list[0][0][0]
        assert "SYS PROMPT" not in write_cmd

    async def test_generate_as_root_wraps_for_non_root_user(self):
        """When SSH user is root, generate() wraps cmd for non-root user."""
        ssh = AsyncMock()
        ssh.hostname = "10.0.0.1"
        ssh.username = "root"  # root user — needs wrapping
        ssh.run_command.side_effect = [
            ("/tmp/prompt\n", "", 0),  # write prompt
            ("review output", "", 0),  # agent run (wrapped)
            ("", "", 0),  # cleanup
        ]
        adapter = CLIAdapter(ssh, "claude")
        adapter.worker_user = "coder"

        result = await adapter.generate(
            "review this code", session_id="sess-123", workspace="/workspace"
        )
        assert result == "review output"

        # The agent command should be wrapped with runuser
        agent_cmd = ssh.run_command.call_args_list[1][0][0]
        assert "runuser -u coder" in agent_cmd
        assert "--resume" in agent_cmd

    async def test_generate_new_session_uses_session_start_command(self):
        """generate() with new_session=True uses generate_session_start (--session-id)."""
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("/tmp/prompt\n", "", 0),  # write prompt
            ("generated output", "", 0),  # agent run
            ("", "", 0),  # cleanup
        ]
        adapter = CLIAdapter(ssh, "claude")

        result = await adapter.generate(
            "plan this task",
            session_id="new-sess-abc",
            new_session=True,
            workspace="/workspace/proj",
        )
        assert result == "generated output"

        # Verify --session-id was used (NOT --resume)
        gen_cmd = ssh.run_command.call_args_list[1][0][0]
        assert "--session-id" in gen_cmd
        assert "--resume" not in gen_cmd
        assert "new-sess-abc" in gen_cmd
        assert "cd /workspace/proj" in gen_cmd

    async def test_generate_with_system_prompt_no_session(self):
        """System prompt IS prepended when no session_id."""
        ssh = AsyncMock()
        ssh.run_command.side_effect = [
            ("/tmp/prompt\n", "", 0),
            ("output", "", 0),
            ("", "", 0),
        ]
        adapter = CLIAdapter(ssh, "claude")

        await adapter.generate(
            "instruction",
            system_prompt="SYS PROMPT",
        )

        write_cmd = ssh.run_command.call_args_list[0][0][0]
        assert "SYS PROMPT" in write_cmd


class TestPlanningSessionContinuity:
    async def test_planning_generates_session_id_for_session_adapter(
        self, db_session, make_task_run, mock_services
    ):
        """Planning phase creates session_id when adapter supports sessions."""
        run = make_task_run(planning_result={"context_docs": ["some context"]})
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "agent/claude@ws-01"
        mock_adapter.supports_session = True
        mock_adapter.generate.return_value = (
            '{"subtasks": [{"id": 1, "title": "Do X"}], "estimated_complexity": "simple"}'
        )
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.planning.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.planning.get_workspace_server_id",
                new=AsyncMock(return_value=42),
            ),
        ):
            await planning.run(run, db_session, mock_services)

        # session_id should be stored in planning_result
        assert "session_id" in run.planning_result
        assert isinstance(run.planning_result["session_id"], str)
        assert len(run.planning_result["session_id"]) == 36  # UUID format

        # generate() should have been called with session_id and new_session=True
        call_kwargs = mock_adapter.generate.call_args[1]
        assert call_kwargs["session_id"] == run.planning_result["session_id"]
        assert call_kwargs["new_session"] is True
        assert call_kwargs["workspace"] == run.workspace_path

    async def test_planning_no_session_id_for_non_session_adapter(
        self, db_session, make_task_run, mock_services
    ):
        """Planning phase skips session_id when adapter doesn't support sessions."""
        run = make_task_run(planning_result={"context_docs": []})
        db_session.add(run)
        await db_session.commit()

        mock_adapter = AsyncMock()
        mock_adapter.provider_name = "ollama/qwen2.5@gpu-01"
        mock_adapter.supports_session = False
        mock_adapter.generate.return_value = '{"subtasks": [], "estimated_complexity": "simple"}'
        mock_services.role_resolver.resolve.return_value = ResolvedRole(adapter=mock_adapter)

        with (
            patch(
                "backend.worker.phases.planning.broadcaster",
                new=MagicMock(log=AsyncMock(), event=AsyncMock()),
            ),
            patch(
                "backend.worker.phases.planning.get_workspace_server_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            await planning.run(run, db_session, mock_services)

        # session_id should NOT be in planning_result
        assert "session_id" not in run.planning_result

        # generate() should NOT have session_id kwarg
        call_kwargs = mock_adapter.generate.call_args[1]
        assert "session_id" not in call_kwargs
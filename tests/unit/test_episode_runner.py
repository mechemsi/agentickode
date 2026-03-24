# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.episode_runner."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.services.episode_runner import EpisodeRunner
from backend.services.stream_monitor import StreamPollResult


@pytest.fixture
def ssh() -> AsyncMock:
    mock = AsyncMock()
    mock.username = "root"
    mock.run_command = AsyncMock(return_value=("", "", 0))
    mock.fire_and_forget = AsyncMock()
    return mock


@pytest.fixture
def runner(ssh: AsyncMock) -> EpisodeRunner:
    return EpisodeRunner(
        ssh=ssh,
        workspace="/home/worker/project",
        worker_user="worker",
        log_fn=lambda msg, **kw: None,
    )


# ---------------------------------------------------------------------------
# git_checkpoint
# ---------------------------------------------------------------------------


class TestGitCheckpoint:
    """Tests for EpisodeRunner.git_checkpoint()."""

    @pytest.mark.asyncio
    async def test_successful_commit_returns_sha(
        self, runner: EpisodeRunner, ssh: AsyncMock
    ) -> None:
        ssh.run_command.side_effect = [
            ("", "", 0),  # git add + commit
            ("abc123def456\n", "", 0),  # git rev-parse HEAD
        ]
        sha = await runner.git_checkpoint("WIP: episode 1")

        assert sha == "abc123def456"
        assert ssh.run_command.call_count == 2

    @pytest.mark.asyncio
    async def test_no_changes_returns_none(self, runner: EpisodeRunner, ssh: AsyncMock) -> None:
        ssh.run_command.return_value = ("", "", 1)  # commit fails (nothing to commit)
        sha = await runner.git_checkpoint("WIP: episode 1")

        assert sha is None

    @pytest.mark.asyncio
    async def test_commit_ok_but_rev_parse_fails(
        self, runner: EpisodeRunner, ssh: AsyncMock
    ) -> None:
        ssh.run_command.side_effect = [
            ("", "", 0),  # commit succeeds
            ("", "", 128),  # rev-parse fails
        ]
        sha = await runner.git_checkpoint("WIP")

        assert sha is None

    @pytest.mark.asyncio
    async def test_wraps_with_runuser_when_root(
        self, runner: EpisodeRunner, ssh: AsyncMock
    ) -> None:
        ssh.run_command.side_effect = [("", "", 0), ("sha\n", "", 0)]
        await runner.git_checkpoint("msg")

        cmd = ssh.run_command.call_args_list[0][0][0]
        assert "runuser -u worker" in cmd

    @pytest.mark.asyncio
    async def test_no_runuser_when_non_root(self, ssh: AsyncMock) -> None:
        ssh.username = "worker"
        runner = EpisodeRunner(ssh=ssh, workspace="/w", worker_user="worker")
        ssh.run_command.side_effect = [("", "", 0), ("sha\n", "", 0)]
        await runner.git_checkpoint("msg")

        cmd = ssh.run_command.call_args_list[0][0][0]
        assert "runuser" not in cmd


# ---------------------------------------------------------------------------
# kill_agent
# ---------------------------------------------------------------------------


class TestKillAgent:
    """Tests for EpisodeRunner.kill_agent()."""

    @pytest.mark.asyncio
    async def test_sends_pkill(self, runner: EpisodeRunner, ssh: AsyncMock) -> None:
        await runner.kill_agent()

        ssh.run_command.assert_called_once()
        cmd = ssh.run_command.call_args[0][0]
        assert "pkill" in cmd
        assert "/home/worker/project" in cmd


# ---------------------------------------------------------------------------
# _build_command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    """Tests for EpisodeRunner._build_command()."""

    def test_new_session_uses_task_template(self, runner: EpisodeRunner) -> None:
        cmd = runner._build_command(
            episode_num=1,
            session_id="sess-123",
            max_turns=30,
            prompt_file="/w/.autodev/ep_1_prompt.md",
            is_new_session=True,
        )
        assert "--max-turns 30" in cmd
        assert "ep_1_prompt.md" in cmd
        # New session should NOT have --resume
        assert "--resume" not in cmd

    def test_resume_session_uses_resume_template(self, runner: EpisodeRunner) -> None:
        cmd = runner._build_command(
            episode_num=2,
            session_id="sess-456",
            max_turns=20,
            prompt_file="/w/.autodev/ep_2_prompt.md",
            is_new_session=False,
        )
        assert "--max-turns 20" in cmd
        assert "--resume sess-456" in cmd

    def test_episode_num_in_output_path(self, runner: EpisodeRunner) -> None:
        cmd = runner._build_command(
            episode_num=3,
            session_id="s",
            max_turns=10,
            prompt_file="/w/p.md",
            is_new_session=True,
        )
        assert "episode_3.jsonl" in cmd


# ---------------------------------------------------------------------------
# run_episode (integration-level with mocked internals)
# ---------------------------------------------------------------------------


class TestRunEpisode:
    """Tests for EpisodeRunner.run_episode()."""

    @pytest.mark.asyncio
    @patch("backend.services.episode_runner.check_stall", new_callable=AsyncMock)
    @patch("backend.services.episode_runner.poll_stream", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_successful_completion(
        self,
        mock_sleep: AsyncMock,
        mock_poll: AsyncMock,
        mock_stall: AsyncMock,
        runner: EpisodeRunner,
        ssh: AsyncMock,
    ) -> None:
        """Agent writes exit code 0, final poll shows completed."""
        # _write_remote_file, chown, fire_and_forget are on ssh
        # _build_prompt reads agent_prompt.md
        ssh.run_command.side_effect = [
            ("Original prompt", "", 0),  # cat agent_prompt.md (_build_prompt)
            ("", "", 0),  # _write_remote_file
            ("", "", 0),  # chown
            # _monitor_episode loop:
            ("0\n", "", 0),  # _read_exit_code -> 0
            # git_checkpoint:
            ("", "", 0),  # git add + commit
            ("deadbeef\n", "", 0),  # git rev-parse HEAD
        ]

        # Final poll after exit code is found
        mock_poll.return_value = StreamPollResult(
            new_lines=5,
            next_offset=6,
            turn_count=3,
            context_usage_pct=45.0,
            completed=True,
            result_text="All done",
        )
        mock_stall.return_value = False

        result = await runner.run_episode(
            episode_num=1, session_id="sess-1", max_turns=30, is_new_session=True
        )

        assert result.completed is True
        assert result.checkpoint_sha == "deadbeef"
        assert result.turn_count == 3
        ssh.fire_and_forget.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.services.episode_runner.check_stall", new_callable=AsyncMock)
    @patch("backend.services.episode_runner.poll_stream", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_stall_detection(
        self,
        mock_sleep: AsyncMock,
        mock_poll: AsyncMock,
        mock_stall: AsyncMock,
        runner: EpisodeRunner,
        ssh: AsyncMock,
    ) -> None:
        """Agent stalls and monitor detects it."""
        ssh.run_command.side_effect = [
            ("Prompt", "", 0),  # cat agent_prompt.md
            ("", "", 0),  # _write_remote_file
            ("", "", 0),  # chown
            # _monitor_episode:
            ("", "", 1),  # _read_exit_code -> None (no file)
            # git_checkpoint:
            ("", "", 0),
            ("sha1\n", "", 0),
        ]

        mock_poll.return_value = StreamPollResult(
            new_lines=0,
            next_offset=1,
            turn_count=0,
            context_usage_pct=10.0,
        )
        mock_stall.return_value = True  # Stall detected

        result = await runner.run_episode(
            episode_num=1, session_id="s", max_turns=30, is_new_session=True
        )

        assert result.stalled is True
        assert result.completed is False

    @pytest.mark.asyncio
    @patch("backend.services.episode_runner.check_stall", new_callable=AsyncMock)
    @patch("backend.services.episode_runner.poll_stream", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_context_exhaustion(
        self,
        mock_sleep: AsyncMock,
        mock_poll: AsyncMock,
        mock_stall: AsyncMock,
        runner: EpisodeRunner,
        ssh: AsyncMock,
    ) -> None:
        """Context usage hits 90%+, episode is terminated early."""
        ssh.run_command.side_effect = [
            ("Prompt", "", 0),  # cat agent_prompt.md
            ("", "", 0),  # _write_remote_file
            ("", "", 0),  # chown
            # _monitor_episode:
            ("", "", 1),  # _read_exit_code -> None
            # kill_agent (after context exhaustion):
            ("", "", 0),  # pkill
            # git_checkpoint:
            ("", "", 0),
            ("sha2\n", "", 0),
        ]

        mock_poll.return_value = StreamPollResult(
            new_lines=5,
            next_offset=6,
            turn_count=4,
            context_usage_pct=92.0,
        )
        mock_stall.return_value = False

        result = await runner.run_episode(
            episode_num=1, session_id="s", max_turns=30, is_new_session=True
        )

        assert result.context_exhausted is True


# ---------------------------------------------------------------------------
# _wrap_for_user
# ---------------------------------------------------------------------------


class TestWrapForUser:
    """Tests for EpisodeRunner._wrap_for_user()."""

    def test_root_wraps_with_runuser(self, runner: EpisodeRunner) -> None:
        wrapped = runner._wrap_for_user("echo hi")
        assert "runuser -u worker" in wrapped
        assert "echo hi" in wrapped

    def test_non_root_passes_through(self, ssh: AsyncMock) -> None:
        ssh.username = "worker"
        r = EpisodeRunner(ssh=ssh, workspace="/w", worker_user="worker")
        wrapped = r._wrap_for_user("echo hi")
        assert wrapped == "echo hi"

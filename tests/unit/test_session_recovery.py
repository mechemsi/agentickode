# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.session_recovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.session_recovery import RecoveryContext, SessionRecoveryService


@pytest.fixture()
def ssh():
    mock = AsyncMock()
    mock.run_command = AsyncMock()
    return mock


@pytest.fixture()
def service(ssh):
    return SessionRecoveryService(ssh=ssh, workspace="/tmp/ws")


def _make_episode(
    episode_number: int = 1,
    git_checkpoint_sha: str | None = "abc123",
    summary: str = "",
):
    ep = MagicMock()
    ep.episode_number = episode_number
    ep.git_checkpoint_sha = git_checkpoint_sha
    ep.summary = summary
    return ep


@pytest.mark.asyncio
async def test_is_agent_alive_returns_false_when_exit_code_exists(ssh, service):
    """If exit code file exists, process has finished → not alive."""
    ssh.run_command.return_value = ("0", "", 0)

    result = await service.is_agent_alive(1)

    assert result is False


@pytest.mark.asyncio
async def test_is_agent_alive_returns_true_when_process_running(ssh, service):
    """If no exit code but pgrep finds a process → alive."""
    ssh.run_command.side_effect = [
        # cat exit code → file not found
        ("", "", 1),
        # pgrep → finds process
        ("12345", "", 0),
    ]

    result = await service.is_agent_alive(1)

    assert result is True


@pytest.mark.asyncio
async def test_is_agent_alive_returns_false_when_nothing_found(ssh, service):
    """If no exit code and no pgrep match → not alive."""
    ssh.run_command.side_effect = [
        # cat exit code → file not found
        ("", "", 1),
        # pgrep → no match
        ("", "", 1),
    ]

    result = await service.is_agent_alive(1)

    assert result is False


@pytest.mark.asyncio
async def test_recover_resets_dirty_workspace_and_builds_context(ssh, service):
    """recover resets workspace when dirty and builds context via compactor."""
    last_episode = _make_episode(episode_number=1, git_checkpoint_sha="abc123")

    ssh.run_command.side_effect = [
        # git status --porcelain → dirty
        ("M src/main.py", "", 0),
        # git checkout -- . && git clean -fd
        ("", "", 0),
        # compact_episode: git log
        ("abc1234 initial commit", "", 0),
        # compact_episode: git diff --name-only
        ("src/main.py", "", 0),
        # compact_episode: cat JSONL
        ("", "", 1),
    ]

    result = await service.recover(last_episode, session_id="sess-1")

    assert isinstance(result, RecoveryContext)
    assert result.session_id == "sess-1"
    assert result.last_episode_num == 1
    assert result.checkpoint_sha == "abc123"
    assert "Episode 1 Summary" in result.summary


@pytest.mark.asyncio
async def test_recover_uses_existing_episode_summary(ssh, service):
    """recover uses last_episode.summary if available, skipping compaction."""
    last_episode = _make_episode(
        episode_number=2,
        git_checkpoint_sha="def456",
        summary="Episode 2 completed auth work",
    )

    ssh.run_command.side_effect = [
        # git status --porcelain → clean
        ("", "", 0),
    ]

    result = await service.recover(last_episode, session_id="sess-2")

    assert result.summary == "Episode 2 completed auth work"
    assert result.last_episode_num == 2
    # Only one SSH call (git status), no compaction calls
    assert ssh.run_command.call_count == 1

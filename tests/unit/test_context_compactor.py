# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.context_compactor."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from backend.services.context_compactor import ContextCompactor


@pytest.fixture()
def ssh():
    mock = AsyncMock()
    mock.run_command = AsyncMock()
    return mock


@pytest.fixture()
def compactor(ssh):
    return ContextCompactor(ssh=ssh, workspace="/tmp/ws")


@pytest.mark.asyncio
async def test_compact_episode_returns_summary_with_commits_and_files(ssh, compactor):
    """compact_episode builds summary from git log, diff, and JSONL."""
    ssh.run_command.side_effect = [
        # git log
        ("abc1234 feat: add auth\ndef5678 fix: typo", "", 0),
        # git diff --name-only
        ("src/auth.py\nsrc/models.py", "", 0),
        # cat JSONL (for _extract_decisions)
        ("", "", 1),
    ]

    result = await compactor.compact_episode(1)

    assert "Episode 1 Summary" in result
    assert "abc1234 feat: add auth" in result
    assert "src/auth.py" in result
    assert "Recent commits" in result
    assert "Files changed" in result


@pytest.mark.asyncio
async def test_compact_episode_handles_ssh_errors_gracefully(ssh, compactor):
    """compact_episode still produces output when git commands fail."""
    ssh.run_command.side_effect = [
        # git log fails → fallback text
        ("(no commits)", "", 1),
        # git diff fails → fallback text
        ("(unknown)", "", 1),
        # JSONL read fails
        ("", "", 1),
    ]

    result = await compactor.compact_episode(2)

    assert "Episode 2 Summary" in result
    assert "(no commits)" in result
    assert "(unknown)" in result


@pytest.mark.asyncio
async def test_build_continuation_prompt_includes_all_sections(ssh, compactor):
    """build_continuation_prompt includes task, summary, status, instructions."""
    ssh.run_command.return_value = ("M src/main.py", "", 0)

    result = await compactor.build_continuation_prompt(
        task_description="Implement feature X",
        episodes_summary="Episode 1: set up scaffolding",
        episode_num=2,
    )

    assert "Continuation — Episode 2" in result
    assert "Implement feature X" in result
    assert "Episode 1: set up scaffolding" in result
    assert "M src/main.py" in result
    assert "Continue working on the original task" in result


@pytest.mark.asyncio
async def test_extract_decisions_extracts_assistant_messages(ssh, compactor):
    """_extract_decisions parses JSONL and returns assistant messages."""
    lines = [
        json.dumps({"type": "assistant", "content": "A" * 100}),
        json.dumps({"type": "user", "content": "short user msg"}),
        json.dumps({"type": "assistant", "content": "B" * 60}),
        json.dumps({"type": "assistant", "content": "tiny"}),  # <50 chars, skipped
    ]
    ssh.run_command.return_value = ("\n".join(lines), "", 0)

    result = await compactor._extract_decisions(1)

    assert "A" * 100 in result
    assert "B" * 60 in result
    # Short message (<50 chars) should be excluded
    assert "tiny" not in result
    # User messages should be excluded
    assert "short user msg" not in result

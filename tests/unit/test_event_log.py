# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.event_log."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from backend.services.event_log import EventLog


@pytest.fixture()
def ssh():
    mock = AsyncMock()
    mock.run_command = AsyncMock(return_value=("", "", 0))
    return mock


@pytest.fixture()
def event_log(ssh):
    return EventLog(ssh=ssh, workspace="/tmp/ws")


@pytest.mark.asyncio
async def test_append_writes_json_to_file_via_ssh(ssh, event_log):
    """append serializes event as JSON and echoes it to the remote file."""
    await event_log.append("episode_started", {"episode": 1})

    ssh.run_command.assert_called_once()
    call_args = ssh.run_command.call_args
    cmd = call_args[0][0]

    # Command should echo JSON to the event log path
    assert "echo" in cmd
    assert "event_log.jsonl" in cmd
    # The JSON should contain the event type and data
    assert "episode_started" in cmd
    assert '"episode":1' in cmd or '"episode": 1' in cmd


@pytest.mark.asyncio
async def test_append_without_data(ssh, event_log):
    """append works when data is None."""
    await event_log.append("agent_killed")

    ssh.run_command.assert_called_once()
    cmd = ssh.run_command.call_args[0][0]
    assert "agent_killed" in cmd


@pytest.mark.asyncio
async def test_read_all_parses_jsonl_correctly(ssh, event_log):
    """read_all parses each JSONL line into a dict."""
    lines = [
        json.dumps({"type": "episode_started", "timestamp": "2026-01-01T00:00:00"}),
        json.dumps({"type": "episode_completed", "timestamp": "2026-01-01T01:00:00"}),
    ]
    ssh.run_command.return_value = ("\n".join(lines), "", 0)

    events = await event_log.read_all()

    assert len(events) == 2
    assert events[0]["type"] == "episode_started"
    assert events[1]["type"] == "episode_completed"


@pytest.mark.asyncio
async def test_read_all_returns_empty_list_when_file_missing(ssh, event_log):
    """read_all returns [] when cat fails (file doesn't exist)."""
    ssh.run_command.return_value = ("", "", 1)

    events = await event_log.read_all()

    assert events == []


@pytest.mark.asyncio
async def test_read_all_skips_invalid_json_lines(ssh, event_log):
    """read_all skips lines that are not valid JSON."""
    lines = [
        json.dumps({"type": "episode_started"}),
        "not valid json",
        json.dumps({"type": "git_checkpoint"}),
    ]
    ssh.run_command.return_value = ("\n".join(lines), "", 0)

    events = await event_log.read_all()

    assert len(events) == 2
    assert events[0]["type"] == "episode_started"
    assert events[1]["type"] == "git_checkpoint"


@pytest.mark.asyncio
async def test_read_since_reads_from_correct_offset(ssh, event_log):
    """read_since uses tail -n + to skip earlier lines."""
    line = json.dumps({"type": "recovery_started"})
    ssh.run_command.return_value = (line, "", 0)

    events = await event_log.read_since(after_line=5)

    assert len(events) == 1
    assert events[0]["type"] == "recovery_started"

    # Verify the tail command uses the correct offset (after_line + 1)
    cmd = ssh.run_command.call_args[0][0]
    assert "tail -n +6" in cmd


@pytest.mark.asyncio
async def test_read_since_returns_empty_on_failure(ssh, event_log):
    """read_since returns [] when tail command fails."""
    ssh.run_command.return_value = ("", "", 1)

    events = await event_log.read_since(after_line=10)

    assert events == []

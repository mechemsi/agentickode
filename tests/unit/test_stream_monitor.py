# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.stream_monitor."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from backend.services.stream_monitor import check_stall, poll_stream


@pytest.fixture
def ssh() -> AsyncMock:
    mock = AsyncMock()
    mock.username = "root"
    mock.run_command = AsyncMock(return_value=("", "", 0))
    return mock


# ---------------------------------------------------------------------------
# poll_stream
# ---------------------------------------------------------------------------


class TestPollStream:
    """Tests for poll_stream()."""

    @pytest.mark.asyncio
    async def test_empty_output_nonzero_rc(self, ssh: AsyncMock) -> None:
        ssh.run_command.return_value = ("", "", 1)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.new_lines == 0
        assert result.next_offset == 1
        assert result.completed is False

    @pytest.mark.asyncio
    async def test_empty_stdout(self, ssh: AsyncMock) -> None:
        ssh.run_command.return_value = ("", "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.new_lines == 0
        assert result.next_offset == 1

    @pytest.mark.asyncio
    async def test_assistant_turn_counting(self, ssh: AsyncMock) -> None:
        lines = "\n".join(
            [
                json.dumps({"type": "assistant", "content": "Hello"}),
                json.dumps({"type": "assistant", "content": "Working on it"}),
                json.dumps({"type": "user", "content": "ok"}),
            ]
        )
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.turn_count == 2
        assert result.new_lines == 3
        assert result.completed is False

    @pytest.mark.asyncio
    async def test_offset_advances(self, ssh: AsyncMock) -> None:
        lines = "\n".join(
            [
                json.dumps({"type": "assistant", "content": "a"}),
                json.dumps({"type": "assistant", "content": "b"}),
            ]
        )
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 5)

        assert result.next_offset == 7  # 5 + 2 lines

    @pytest.mark.asyncio
    async def test_result_event_sets_completed(self, ssh: AsyncMock) -> None:
        lines = "\n".join(
            [
                json.dumps({"type": "assistant", "content": "done"}),
                json.dumps({"type": "result", "result": "Task complete"}),
            ]
        )
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.completed is True
        assert result.result_text == "Task complete"
        assert result.turn_count == 1

    @pytest.mark.asyncio
    async def test_result_event_fallback_content_field(self, ssh: AsyncMock) -> None:
        lines = json.dumps({"type": "result", "content": "Fallback text"})
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.completed is True
        assert result.result_text == "Fallback text"

    @pytest.mark.asyncio
    async def test_context_window_system_event(self, ssh: AsyncMock) -> None:
        lines = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "context_window", "usage_pct": 72.5}),
                json.dumps({"type": "assistant", "content": "hi"}),
            ]
        )
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.context_usage_pct == 72.5

    @pytest.mark.asyncio
    async def test_context_usage_integer(self, ssh: AsyncMock) -> None:
        lines = json.dumps({"type": "system", "subtype": "context_window", "usage_pct": 85})
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.context_usage_pct == 85.0

    @pytest.mark.asyncio
    async def test_error_events_captured(self, ssh: AsyncMock) -> None:
        lines = json.dumps({"type": "error", "message": "rate limited"})
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.errors == ["rate limited"]

    @pytest.mark.asyncio
    async def test_malformed_json_skipped(self, ssh: AsyncMock) -> None:
        lines = "not-json\n" + json.dumps({"type": "assistant", "content": "ok"})
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.turn_count == 1
        assert result.new_lines == 2

    @pytest.mark.asyncio
    async def test_non_dict_json_skipped(self, ssh: AsyncMock) -> None:
        lines = "[1, 2, 3]\n" + json.dumps({"type": "assistant", "content": "ok"})
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 1)

        assert result.turn_count == 1

    @pytest.mark.asyncio
    async def test_offset_clamped_to_one(self, ssh: AsyncMock) -> None:
        lines = json.dumps({"type": "assistant", "content": "x"})
        ssh.run_command.return_value = (lines, "", 0)
        result = await poll_stream(ssh, "/tmp/ep.jsonl", 0)

        # offset=0 should be clamped to 1
        assert result.next_offset == 2
        ssh.run_command.assert_called_once()
        call_cmd = ssh.run_command.call_args[0][0]
        assert "tail -n +1" in call_cmd


# ---------------------------------------------------------------------------
# check_stall
# ---------------------------------------------------------------------------


class TestCheckStall:
    """Tests for check_stall()."""

    @pytest.mark.asyncio
    async def test_file_not_found(self, ssh: AsyncMock) -> None:
        ssh.run_command.return_value = ("", "", 1)
        assert await check_stall(ssh, "/tmp/ep.jsonl", 600) is False

    @pytest.mark.asyncio
    async def test_file_recently_modified(self, ssh: AsyncMock) -> None:
        """File modified 10s ago with a 600s timeout -> not stalled."""
        ssh.run_command.side_effect = [
            ("1000000", "", 0),  # stat mtime
            ("1000010", "", 0),  # date +%s  (10s later)
        ]
        assert await check_stall(ssh, "/tmp/ep.jsonl", 600) is False

    @pytest.mark.asyncio
    async def test_file_stale(self, ssh: AsyncMock) -> None:
        """File modified 700s ago with a 600s timeout -> stalled."""
        ssh.run_command.side_effect = [
            ("1000000", "", 0),  # stat mtime
            ("1000700", "", 0),  # date +%s  (700s later)
        ]
        assert await check_stall(ssh, "/tmp/ep.jsonl", 600) is True

    @pytest.mark.asyncio
    async def test_stat_returns_garbage(self, ssh: AsyncMock) -> None:
        ssh.run_command.return_value = ("not-a-number", "", 0)
        assert await check_stall(ssh, "/tmp/ep.jsonl", 600) is False

    @pytest.mark.asyncio
    async def test_date_command_fails(self, ssh: AsyncMock) -> None:
        ssh.run_command.side_effect = [
            ("1000000", "", 0),  # stat mtime ok
            ("", "", 1),  # date fails
        ]
        assert await check_stall(ssh, "/tmp/ep.jsonl", 600) is False

    @pytest.mark.asyncio
    async def test_exact_boundary_not_stalled(self, ssh: AsyncMock) -> None:
        """age == timeout -> not stalled (needs to exceed)."""
        ssh.run_command.side_effect = [
            ("1000000", "", 0),
            ("1000600", "", 0),  # exactly 600s
        ]
        assert await check_stall(ssh, "/tmp/ep.jsonl", 600) is False

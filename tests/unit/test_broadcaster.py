# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for the WebSocket broadcaster."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.worker.broadcaster import Broadcaster, make_log_metadata


class TestBroadcaster:
    @pytest.fixture()
    def bc(self):
        """Fresh broadcaster per test."""
        return Broadcaster()

    async def test_subscribe_and_unsubscribe_run(self, bc):
        queue = asyncio.Queue()
        bc.subscribe_run(1, queue)
        assert queue in bc._run_subs[1]
        bc.unsubscribe_run(1, queue)
        assert 1 not in bc._run_subs

    async def test_subscribe_and_unsubscribe_global(self, bc):
        queue = asyncio.Queue()
        bc.subscribe_global(queue)
        assert queue in bc._global_subs
        bc.unsubscribe_global(queue)
        assert queue not in bc._global_subs

    async def test_log_broadcasts_to_run_subscribers(self, bc):
        queue = asyncio.Queue()
        bc.subscribe_run(1, queue)

        with patch("backend.worker.broadcaster.async_session") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await bc.log(run_id=1, message="test msg", level="info")

        msg = queue.get_nowait()
        assert msg["message"] == "test msg"
        assert msg["level"] == "info"
        assert msg["run_id"] == 1
        assert msg["type"] == "log"

    async def test_log_with_metadata_broadcasts_metadata(self, bc):
        queue = asyncio.Queue()
        bc.subscribe_run(1, queue)

        meta = {"category": "ssh_command", "command": "git status"}
        with patch("backend.worker.broadcaster.async_session") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await bc.log(run_id=1, message="running git", level="info", metadata=meta)

        msg = queue.get_nowait()
        assert msg["metadata_"] == meta
        assert msg["message"] == "running git"

    async def test_log_without_metadata_omits_key(self, bc):
        queue = asyncio.Queue()
        bc.subscribe_run(1, queue)

        with patch("backend.worker.broadcaster.async_session") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await bc.log(run_id=1, message="no meta", level="info")

        msg = queue.get_nowait()
        assert "metadata_" not in msg

    async def test_event_broadcasts_to_global_subscribers(self, bc):
        global_q = asyncio.Queue()
        bc.subscribe_global(global_q)

        await bc.event(run_id=5, event_type="status_change", data={"status": "running"})

        msg = global_q.get_nowait()
        assert msg["run_id"] == 5
        assert msg["type"] == "status_change"
        assert msg["status"] == "running"

    async def test_log_does_not_leak_across_runs(self, bc):
        q1 = asyncio.Queue()
        q2 = asyncio.Queue()
        bc.subscribe_run(1, q1)
        bc.subscribe_run(2, q2)

        with patch("backend.worker.broadcaster.async_session") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await bc.log(run_id=1, message="only for run 1", level="info")

        assert q1.qsize() == 1
        assert q2.qsize() == 0

    async def test_full_queue_does_not_raise(self, bc):
        """If a subscriber queue is full, broadcast should not raise."""
        small_q = asyncio.Queue(maxsize=1)
        small_q.put_nowait({"old": "msg"})  # fill the queue
        bc.subscribe_run(1, small_q)

        with patch("backend.worker.broadcaster.async_session") as mock_session_factory:
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            # Should not raise even though queue is full
            await bc.log(run_id=1, message="overflow", level="info")

        assert small_q.qsize() == 1  # still just the old message


class TestMakeLogMetadata:
    def test_basic_metadata(self):
        meta = make_log_metadata("ssh_command", command="git status")
        assert meta["category"] == "ssh_command"
        assert meta["command"] == "git status"

    def test_prompt_truncation(self):
        long_prompt = "x" * 15_000
        meta = make_log_metadata("prompt", prompt_text=long_prompt)
        assert len(meta["prompt_text"]) == 10_000
        assert meta["prompt_text_truncated"] is True
        assert meta["prompt_text_original_length"] == 15_000

    def test_output_truncation(self):
        long_output = "y" * 5_000
        meta = make_log_metadata("response", response_text=long_output)
        assert len(meta["response_text"]) == 2_000
        assert meta["response_text_truncated"] is True
        assert meta["response_text_original_length"] == 5_000

    def test_no_truncation_under_limit(self):
        short = "hello"
        meta = make_log_metadata("prompt", prompt_text=short)
        assert meta["prompt_text"] == "hello"
        assert "prompt_text_truncated" not in meta

    def test_non_string_values_passed_through(self):
        meta = make_log_metadata("ssh_command", exit_code=0, command="ls")
        assert meta["exit_code"] == 0
        assert meta["command"] == "ls"

    def test_system_prompt_uses_prompt_limit(self):
        long = "z" * 15_000
        meta = make_log_metadata("system_prompt", system_prompt_text=long)
        assert len(meta["system_prompt_text"]) == 10_000
        assert meta["system_prompt_text_truncated"] is True

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for QueueService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.queue_service import QueueService


@pytest.fixture
def mock_redis():
    """Create a mock Redis client with common set operations."""
    r = AsyncMock()
    r.ping = AsyncMock()
    r.scard = AsyncMock(return_value=0)
    r.sadd = AsyncMock()
    r.srem = AsyncMock()
    r.hset = AsyncMock()
    r.hgetall = AsyncMock(return_value={})
    r.delete = AsyncMock()
    r.smembers = AsyncMock(return_value=set())
    return r


@pytest.fixture
def queue_svc(mock_redis):
    """QueueService with injected mock Redis."""
    svc = QueueService()
    svc._redis = mock_redis
    return svc


class TestQueueService:
    async def test_connect(self):
        svc = QueueService()
        mock_r = AsyncMock()
        mock_r.ping = AsyncMock()
        with patch("backend.services.queue_service.redis.from_url", return_value=mock_r):
            await svc.connect()
        mock_r.ping.assert_awaited_once()
        assert svc._redis is mock_r

    async def test_close(self, queue_svc, mock_redis):
        await queue_svc.close()
        mock_redis.aclose.assert_awaited_once()

    async def test_client_raises_when_not_connected(self):
        svc = QueueService()
        with pytest.raises(AssertionError, match="not connected"):
            _ = svc.client

    async def test_get_server_active_count(self, queue_svc, mock_redis):
        mock_redis.scard.return_value = 3
        count = await queue_svc.get_server_active_count(42)
        mock_redis.scard.assert_awaited_once_with("server:42:active_runs")
        assert count == 3

    async def test_acquire_server_slot(self, queue_svc, mock_redis):
        result = await queue_svc.acquire_server_slot(1, 100)
        assert result is True
        mock_redis.sadd.assert_awaited_once_with("server:1:active_runs", "100")

    async def test_release_server_slot(self, queue_svc, mock_redis):
        await queue_svc.release_server_slot(1, 100)
        mock_redis.srem.assert_awaited_once_with("server:1:active_runs", "100")

    async def test_mark_run_started(self, queue_svc, mock_redis):
        await queue_svc.mark_run_started(10, 5)
        mock_redis.hset.assert_awaited_once()
        call_kwargs = mock_redis.hset.call_args
        assert call_kwargs[0][0] == "run:10"
        assert call_kwargs[1]["mapping"]["server_id"] == "5"
        assert call_kwargs[1]["mapping"]["status"] == "running"
        mock_redis.sadd.assert_awaited_once_with("server:5:active_runs", "10")

    async def test_mark_run_completed_with_server_id(self, queue_svc, mock_redis):
        await queue_svc.mark_run_completed(10, server_id=5)
        mock_redis.srem.assert_awaited_once_with("server:5:active_runs", "10")
        mock_redis.delete.assert_awaited_once_with("run:10")

    async def test_mark_run_completed_lookup_server_id(self, queue_svc, mock_redis):
        mock_redis.hgetall.return_value = {"server_id": "7", "status": "running"}
        await queue_svc.mark_run_completed(10)
        mock_redis.hgetall.assert_awaited_once_with("run:10")
        mock_redis.srem.assert_awaited_once_with("server:7:active_runs", "10")

    async def test_get_queue_status(self, queue_svc, mock_redis):
        async def fake_scan_iter(pattern):
            for key in ["server:1:active_runs", "server:2:active_runs"]:
                yield key

        mock_redis.scan_iter = MagicMock(side_effect=fake_scan_iter)
        mock_redis.scard = AsyncMock(side_effect=[2, 0])

        status = await queue_svc.get_queue_status()
        assert status["server_loads"] == {"1": 2}

    async def test_cleanup_stale_entries(self, queue_svc, mock_redis):
        async def fake_scan_iter(pattern):
            yield "server:1:active_runs"

        mock_redis.scan_iter = MagicMock(side_effect=fake_scan_iter)
        mock_redis.smembers.return_value = {"100", "200", "300"}

        # Only run 200 is valid
        await queue_svc.cleanup_stale_entries({200})

        # Should remove 100 and 300
        assert mock_redis.srem.await_count == 2

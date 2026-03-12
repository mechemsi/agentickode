# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for SSH retry with exponential backoff."""

from unittest.mock import AsyncMock, patch

import asyncssh
import pytest

from backend.services.workspace.ssh_service import SSHService


class TestSSHRetry:
    def _make_svc(self):
        return SSHService(hostname="10.0.0.1", port=22, username="root", key_path="/tmp/key")

    @pytest.mark.asyncio
    async def test_connect_with_retry_succeeds_after_transient_failure(self):
        svc = self._make_svc()
        mock_conn = AsyncMock()
        svc._connect = AsyncMock(side_effect=[ConnectionRefusedError("refused"), mock_conn])
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await svc._connect_with_retry()
        assert result is mock_conn
        assert svc._connect.call_count == 2
        mock_sleep.assert_called_once_with(2.0)

    @pytest.mark.asyncio
    async def test_connect_with_retry_gives_up_after_max_retries(self):
        svc = self._make_svc()
        svc._connect = AsyncMock(side_effect=ConnectionRefusedError("refused"))
        with patch("asyncio.sleep", new_callable=AsyncMock), pytest.raises(ConnectionRefusedError):
            await svc._connect_with_retry()
        assert svc._connect.call_count == 3

    @pytest.mark.asyncio
    async def test_connect_with_retry_no_retry_on_auth_error(self):
        svc = self._make_svc()
        svc._connect = AsyncMock(side_effect=asyncssh.PermissionDenied("denied"))
        with pytest.raises(asyncssh.PermissionDenied):
            await svc._connect_with_retry()
        assert svc._connect.call_count == 1

    @pytest.mark.asyncio
    async def test_connect_with_retry_retries_os_error(self):
        svc = self._make_svc()
        mock_conn = AsyncMock()
        svc._connect = AsyncMock(side_effect=[OSError("network unreachable"), mock_conn])
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await svc._connect_with_retry()
        assert result is mock_conn

    @pytest.mark.asyncio
    async def test_connect_with_retry_exponential_delays(self):
        svc = self._make_svc()
        mock_conn = AsyncMock()
        svc._connect = AsyncMock(
            side_effect=[
                ConnectionRefusedError("r1"),
                ConnectionRefusedError("r2"),
                mock_conn,
            ]
        )
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await svc._connect_with_retry()
        assert mock_sleep.call_args_list[0].args == (2.0,)
        assert mock_sleep.call_args_list[1].args == (4.0,)
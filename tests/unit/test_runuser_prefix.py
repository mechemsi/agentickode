# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.workspace.runuser_prefix."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.services.workspace.runuser_prefix import runuser_prefix, wrap_for_user
from backend.services.workspace.usernames import UsernameError


class TestRunuserPrefix:
    async def test_empty_when_no_worker_user(self):
        assert await runuser_prefix(None) == ""
        assert await runuser_prefix("") == ""

    async def test_empty_when_not_root(self):
        with patch("backend.services.workspace.runuser_prefix.os.geteuid", return_value=1000):
            assert await runuser_prefix("domas") == ""

    async def test_empty_when_already_target_user(self):
        # ``getlogin`` returns the target user → no wrap needed.
        with (
            patch("backend.services.workspace.runuser_prefix.os.geteuid", return_value=0),
            patch(
                "backend.services.workspace.runuser_prefix._current_login",
                return_value="domas",
            ),
        ):
            assert await runuser_prefix("domas") == ""

    async def test_wraps_when_root_and_different_user(self):
        with (
            patch("backend.services.workspace.runuser_prefix.os.geteuid", return_value=0),
            patch("backend.services.workspace.runuser_prefix._current_login", return_value="root"),
            patch(
                "backend.services.workspace.runuser_prefix.ensure_local_user",
                new=AsyncMock(return_value=(True, "")),
            ) as mock_ensure,
        ):
            prefix = await runuser_prefix("domas")
        assert prefix.startswith("runuser -l ")
        assert prefix.endswith(" -c ")
        assert "domas" in prefix
        mock_ensure.assert_awaited_once_with("domas")

    async def test_rejects_unsafe_username(self):
        with (
            patch("backend.services.workspace.runuser_prefix.os.geteuid", return_value=0),
            pytest.raises(UsernameError, match="worker_user"),
        ):
            await runuser_prefix("a;rm -rf /")


class TestWrapForUser:
    def test_returns_cmd_when_prefix_empty(self):
        assert wrap_for_user("echo hi", "") == "echo hi"

    def test_quotes_and_appends_when_prefix_set(self):
        out = wrap_for_user("echo 'hi there'", "runuser -l domas -c ")
        assert out.startswith("runuser -l domas -c ")
        # The inner command is single-quoted by shlex; running it via
        # ``-c`` should preserve the original spaces.
        assert "echo" in out
        assert "hi there" in out

    def test_handles_metachars_in_cmd(self):
        # The wrapped command can contain anything (it's all data to
        # runuser -c). shlex.quote guarantees the outer shell parses it
        # as a single argument.
        out = wrap_for_user("ls $HOME; echo end", "runuser -l u -c ")
        # The single-quoted form should appear after ``-c ``.
        assert out.startswith("runuser -l u -c ")

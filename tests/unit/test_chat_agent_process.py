# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.chat.agent_process._maybe_wrap_runuser."""

from unittest.mock import patch

import pytest

from backend.services.chat.agent_process import _maybe_wrap_runuser
from backend.services.workspace.usernames import UsernameError


class TestMaybeWrapRunuser:
    def test_no_op_when_worker_user_unset(self):
        out = _maybe_wrap_runuser("claude -p hi", worker_user=None, platform_url="http://x")
        assert out == "claude -p hi"

    def test_no_op_when_worker_user_empty_string(self):
        out = _maybe_wrap_runuser("claude -p hi", worker_user="", platform_url="http://x")
        assert out == "claude -p hi"

    def test_no_op_when_not_root(self):
        # Non-root invocation: even if worker_user is set, we don't wrap
        # because ``runuser`` would just fail without privileges.
        with patch("backend.services.chat.agent_process.os.geteuid", return_value=1000):
            out = _maybe_wrap_runuser("claude -p hi", worker_user="domas", platform_url="http://x")
        assert out == "claude -p hi"

    def test_wraps_with_runuser_when_root_and_different_user(self):
        with (
            patch("backend.services.chat.agent_process.os.geteuid", return_value=0),
            patch(
                "backend.services.chat.agent_process.os.getlogin",
                side_effect=OSError("no controlling tty"),
            ),
        ):
            out = _maybe_wrap_runuser(
                "claude -p hi", worker_user="domas", platform_url="http://api"
            )
        assert out.startswith("runuser -l domas -c ")
        # The wrapped command includes the env export + original cmd.
        assert "AGENTICKODE_URL" in out
        assert "claude -p hi" in out

    def test_rejects_unsafe_worker_user(self):
        with (
            patch("backend.services.chat.agent_process.os.geteuid", return_value=0),
            pytest.raises(UsernameError, match="worker_user"),
        ):
            _maybe_wrap_runuser("claude -p hi", worker_user="a;rm -rf /", platform_url="http://x")

    def test_chmods_readable_paths(self, tmp_path):
        # Tempfile-style paths the wrapped command will need to read
        # (message file + MCP config). Default tempfile mode is 0600;
        # after wrapping, both files should be world-readable so the
        # worker user can ``cat`` / open them.
        msg = tmp_path / "msg.txt"
        cfg = tmp_path / "mcp.json"
        msg.write_text("hello")
        cfg.write_text("{}")
        msg.chmod(0o600)
        cfg.chmod(0o600)

        with (
            patch("backend.services.chat.agent_process.os.geteuid", return_value=0),
            patch(
                "backend.services.chat.agent_process.os.getlogin",
                side_effect=OSError("no tty"),
            ),
        ):
            _maybe_wrap_runuser(
                "claude -p hi",
                worker_user="domas",
                platform_url="http://x",
                readable_paths=(str(msg), str(cfg)),
            )

        assert msg.stat().st_mode & 0o777 == 0o644
        assert cfg.stat().st_mode & 0o777 == 0o644

    def test_platform_url_is_shell_quoted_inside_wrap(self):
        # A URL with characters that would mis-parse if not quoted.
        with (
            patch("backend.services.chat.agent_process.os.geteuid", return_value=0),
            patch(
                "backend.services.chat.agent_process.os.getlogin",
                side_effect=OSError("no tty"),
            ),
        ):
            out = _maybe_wrap_runuser(
                "claude -p hi",
                worker_user="domas",
                platform_url="http://host:8000/path with space",
            )
        # The whole inner script is shell-quoted by runuser -c, so
        # asserting on the literal URL inside is enough.
        assert "http://host:8000/path with space" in out

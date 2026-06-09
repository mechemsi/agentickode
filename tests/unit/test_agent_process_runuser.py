# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for run-as-user wrapping in chat agent invocation."""

from backend.services.chat.agent_process import _wrap_runuser


class TestWrapRunuser:
    def test_no_user_is_noop(self):
        assert _wrap_runuser("claude -p", None) == "claude -p"
        assert _wrap_runuser("claude -p", "") == "claude -p"

    def test_wraps_with_runuser_login_shell(self):
        wrapped = _wrap_runuser("cat /tmp/m | claude -p", "coder")
        assert wrapped == "runuser -l coder -c 'cat /tmp/m | claude -p'"

    def test_quotes_user_and_command(self):
        wrapped = _wrap_runuser("echo 'hi there'", "weird user")
        # Both the username and the inner command are shell-quoted.
        assert wrapped.startswith("runuser -l 'weird user' -c ")
        # The original command (with its quotes) is preserved inside the wrapper.
        assert "echo" in wrapped and "hi there" in wrapped

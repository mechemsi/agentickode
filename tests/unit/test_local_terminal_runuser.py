# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for run-as-user wrapping of local tmux terminals."""

from backend.api.local_terminals import _tmux
from backend.api.ws import _runuser


class TestTmuxWrap:
    def test_no_user_is_noop(self):
        assert _tmux("tmux new-session -d -s x", None) == "tmux new-session -d -s x"
        assert _tmux("tmux kill-session -t x", "") == "tmux kill-session -t x"

    def test_wraps_with_runuser(self):
        assert (
            _tmux("tmux has-session -t lt-claude-abc", "coder")
            == "runuser -l coder -c 'tmux has-session -t lt-claude-abc'"
        )

    def test_quotes_inner_command(self):
        wrapped = _tmux("tmux send-keys -t x 'claude --resume id' Enter", "coder")
        assert wrapped.startswith("runuser -l coder -c ")
        assert "send-keys" in wrapped


class TestWsRunuser:
    def test_no_user_is_noop(self):
        assert _runuser("tmux attach-session -t x", None) == "tmux attach-session -t x"

    def test_wraps(self):
        assert (
            _runuser("tmux attach-session -t x", "coder")
            == "runuser -l coder -c 'tmux attach-session -t x'"
        )

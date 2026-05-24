# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for WorktreePaths + make_worktree_paths."""

from __future__ import annotations

import pytest

from backend.services.workspace.worktree import make_worktree_paths


class TestMakeWorktreePaths:
    """``make_worktree_paths`` is pure — exercise the naming contract."""

    def test_produces_expected_branch_and_dir(self):
        paths = make_worktree_paths("/srv/repos/foo", 42)
        assert paths.branch.startswith("run/42-")
        assert paths.worktree_dir.startswith("/srv/repos/foo/.worktrees/run-42-")
        # Branch + dir share the suffix
        suffix = paths.branch.split("-", 1)[1]
        assert paths.worktree_dir.endswith(f"run-42-{suffix}")
        assert paths.project_root == "/srv/repos/foo"

    def test_handles_trailing_slash_on_project_root(self):
        paths = make_worktree_paths("/srv/repos/foo/", 1)
        # No double slash in worktree dir
        assert "//" not in paths.worktree_dir
        assert paths.worktree_dir.startswith("/srv/repos/foo/.worktrees/run-1-")

    def test_two_calls_within_same_second_are_identical(self, monkeypatch):
        # Pin time so the timestamp suffix is stable across calls.
        monkeypatch.setattr(
            "backend.services.workspace.worktree.time.time",
            lambda: 1_700_000_000.0,
        )
        a = make_worktree_paths("/srv/repos/foo", 99)
        b = make_worktree_paths("/srv/repos/foo", 99)
        assert a == b
        assert a.branch == "run/99-1700000000"
        assert a.worktree_dir == "/srv/repos/foo/.worktrees/run-99-1700000000"

    @pytest.mark.parametrize(
        "bad_root",
        [
            "; rm -rf /",
            "../etc",
            "relative/path",
            "/path with spaces/foo",
            "/path/with$shellvar",
            "",
        ],
    )
    def test_rejects_unsafe_project_root(self, bad_root):
        with pytest.raises(ValueError, match="unsafe project_root"):
            make_worktree_paths(bad_root, 1)

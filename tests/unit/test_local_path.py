# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for backend.services.workspace.local_path.validate_local_path."""

from unittest.mock import AsyncMock

import pytest

from backend.services.workspace.local_path import LocalPathError, validate_local_path


def _executor(*responses: tuple[str, str, int]):
    """Build a mock CommandExecutor where run_command returns each response in order."""
    exe = AsyncMock()
    exe.run_command = AsyncMock(side_effect=list(responses))
    return exe


class TestValidateLocalPath:
    async def test_rejects_relative_path(self):
        exe = _executor()
        with pytest.raises(LocalPathError, match="unsafe"):
            await validate_local_path(exe, "relative/path")

    async def test_rejects_traversal_chars(self):
        exe = _executor()
        # ``$`` is outside the conservative allowlist.
        with pytest.raises(LocalPathError, match="unsafe"):
            await validate_local_path(exe, "/tmp/$evil")

    async def test_rejects_missing_directory(self):
        # First check (``test -d``) returns rc=1.
        exe = _executor(("", "", 1))
        with pytest.raises(LocalPathError, match="does not exist"):
            await validate_local_path(exe, "/home/u/missing")

    async def test_rejects_non_git_dir(self):
        # ``test -d`` succeeds, ``test -e .git`` fails.
        exe = _executor(("", "", 0), ("", "", 1))
        with pytest.raises(LocalPathError, match="not a git repo"):
            await validate_local_path(exe, "/home/u/notgit")

    async def test_rejects_dirty_tree(self):
        # ``test -d`` 0, ``test -e .git`` 0, ``git status --porcelain`` returns dirty lines.
        exe = _executor(
            ("", "", 0),
            ("", "", 0),
            (" M backend/main.py\n?? new.py\n", "", 0),
        )
        with pytest.raises(LocalPathError, match="uncommitted changes"):
            await validate_local_path(exe, "/home/u/dirty")

    async def test_rejects_git_status_failure(self):
        exe = _executor(("", "", 0), ("", "", 0), ("", "fatal: bad repo", 128))
        with pytest.raises(LocalPathError, match="git status failed"):
            await validate_local_path(exe, "/home/u/badrepo")

    async def test_success_returns_status_struct(self):
        exe = _executor(("", "", 0), ("", "", 0), ("", "", 0))
        status = await validate_local_path(exe, "/home/u/clean")
        assert status.path == "/home/u/clean"
        assert status.exists is True
        assert status.is_git_repo is True
        assert status.is_clean is True
        assert status.dirty_files == ()

    async def test_strips_trailing_slash(self):
        exe = _executor(("", "", 0), ("", "", 0), ("", "", 0))
        status = await validate_local_path(exe, "/home/u/clean/")
        assert status.path == "/home/u/clean"

    async def test_dirty_message_includes_sample(self):
        many_dirty = "\n".join(f" M file{i}.py" for i in range(7)) + "\n"
        exe = _executor(("", "", 0), ("", "", 0), (many_dirty, "", 0))
        with pytest.raises(LocalPathError) as exc:
            await validate_local_path(exe, "/home/u/big")
        msg = str(exc.value)
        assert "file0.py" in msg
        assert "+4 more" in msg

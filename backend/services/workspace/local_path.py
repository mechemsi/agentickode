# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pre-flight validation for ``ProjectConfig.local_path``.

When a project is configured with ``local_path``, ``workspace_setup`` skips
the clone/fetch step entirely and operates on the existing folder. Before
that can happen, we check four invariants:

1. The path is absolute and matches the same conservative allowlist used by
   ``worktree.make_worktree_paths`` (no traversal, ASCII + ``./-_``).
2. The directory exists on the workspace server.
3. It contains a ``.git`` entry (file or dir — git worktrees use a file).
4. The working tree is clean (``git status --porcelain`` is empty).

The dirty-tree check is the one the operator is most likely to trip on —
this matches the resolved policy: refuse to start rather than risk stomping
on the user's uncommitted edits.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from backend.services.workspace.command_executor import CommandExecutor

# Same allowlist as worktree.py so a path that survives this check is safe
# to pass to ``make_worktree_paths`` later.
_PATH_RE = re.compile(r"^/[A-Za-z0-9_./\-]+$")

_CHECK_TIMEOUT = 15


class LocalPathError(ValueError):
    """Raised when ``local_path`` fails pre-flight validation."""


@dataclass(frozen=True)
class LocalPathStatus:
    path: str
    exists: bool
    is_git_repo: bool
    is_clean: bool
    dirty_files: tuple[str, ...] = ()


async def validate_local_path(executor: CommandExecutor, path: str) -> LocalPathStatus:
    """Validate ``path`` for use as a project's pre-cloned workspace.

    Raises ``LocalPathError`` for the first failed invariant. On success
    returns a status struct the caller can log (e.g. into the workspace
    setup step result).
    """
    if not _PATH_RE.match(path):
        raise LocalPathError(f"unsafe local_path: {path!r}")
    normalized = path.rstrip("/") or "/"

    # 1. Directory exists?
    cmd = f"test -d {shlex.quote(normalized)}"
    _, _, rc = await executor.run_command(cmd, timeout=_CHECK_TIMEOUT)
    if rc != 0:
        raise LocalPathError(f"local_path does not exist: {normalized}")

    # 2. Is it a git repo? ``.git`` can be a dir (normal repo) or a file
    # (worktree / submodule) — ``test -e`` covers both.
    cmd = f"test -e {shlex.quote(normalized + '/.git')}"
    _, _, rc = await executor.run_command(cmd, timeout=_CHECK_TIMEOUT)
    if rc != 0:
        raise LocalPathError(f"local_path is not a git repo (no .git): {normalized}")

    # 3. Working tree clean? Use ``--porcelain=v1`` to get a stable, empty
    # output on clean trees regardless of git version.
    cmd = f"git -C {shlex.quote(normalized)} status --porcelain=v1"
    stdout, stderr, rc = await executor.run_command(cmd, timeout=_CHECK_TIMEOUT)
    if rc != 0:
        raise LocalPathError(
            f"git status failed for {normalized}: {stderr.strip() or stdout.strip()}"
        )
    dirty = tuple(line for line in stdout.splitlines() if line.strip())
    if dirty:
        sample = ", ".join(dirty[:3])
        more = f" (+{len(dirty) - 3} more)" if len(dirty) > 3 else ""
        raise LocalPathError(
            f"local_path has uncommitted changes — commit or stash before running: {sample}{more}"
        )

    return LocalPathStatus(
        path=normalized,
        exists=True,
        is_git_repo=True,
        is_clean=True,
        dirty_files=(),
    )

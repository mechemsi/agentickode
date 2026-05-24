# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Worktree path construction.

Adapted from myDash's ``host-gateway/app/fix_issue.py`` — same shape
(timestamp suffix, ``.worktrees/`` inside project dir, pure naming
function separate from IO). A follow-up commit adds the
``WorktreeManager`` service that consumes these paths over a
``CommandExecutor``.

Autodev workspaces live on a remote workspace server reached over SSH,
so we don't need myDash's ``setpriv --reuid=1000`` wrapping — we
already SSH as the right user.

Public surface:
* ``make_worktree_paths(project_root, run_id)`` — pure, IO-free.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

# Conservative path allowlist. Callers shell-quote on interpolation, so
# this is belt-and-suspenders — but a malicious project root is
# rejected up front rather than passed through into a ``git -C`` argv.
_PATH_RE = re.compile(r"^/[A-Za-z0-9_./\-]+$")


@dataclass(frozen=True)
class WorktreePaths:
    """Computed paths for a per-run worktree.

    Field order matches the JSON shape stored in
    ``TaskRun.workspace_result['worktree_paths']`` so finalization can
    rehydrate with ``WorktreePaths(**stored)``.
    """

    branch: str  # "run/<run_id>-<ts>"
    worktree_dir: str  # "<project_root>/.worktrees/run-<run_id>-<ts>"
    project_root: str  # base repo where ``git worktree add`` runs


def make_worktree_paths(project_root: str, run_id: int) -> WorktreePaths:
    """Compute branch + worktree paths for a run. Pure, IO-free.

    The timestamp suffix ensures retrying the same run does not collide
    with an orphaned worktree dir on disk. Branch and dir share the
    suffix so an operator can match them at a glance.
    """
    if not _PATH_RE.match(project_root):
        raise ValueError(f"unsafe project_root: {project_root!r}")
    ts = int(time.time())
    branch = f"run/{run_id}-{ts}"
    worktree_dir = f"{project_root.rstrip('/')}/.worktrees/run-{run_id}-{ts}"
    return WorktreePaths(branch=branch, worktree_dir=worktree_dir, project_root=project_root)

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Worktree path construction + management.

Adapted from myDash's ``host-gateway/app/fix_issue.py`` — same shape
(timestamp suffix, ``.worktrees/`` inside project dir, pure naming
function separate from IO) but driven through ``CommandExecutor``
instead of host-side setpriv subprocess calls. Autodev workspaces live
on a remote workspace server reached over SSH, so we don't need the
``setpriv --reuid=1000`` wrapping — we already SSH as the right user.

Public surface:
* ``make_worktree_paths(project_root, run_id)`` — pure, IO-free.
* ``WorktreeManager(executor)`` — create/remove/list via a
  ``CommandExecutor`` (local subprocess or SSH transport).
"""

from __future__ import annotations

import logging
import re
import shlex
import time
from dataclasses import dataclass

from backend.services.workspace.command_executor import CommandExecutor

logger = logging.getLogger("agentickode.worktree")

# Conservative path allowlist. The CommandExecutor APIs take a single
# command string and we use shlex.quote on every interpolation, so this
# is belt-and-suspenders — but a malicious project root would still be
# rejected up front rather than passed through into a `git -C` argv.
_PATH_RE = re.compile(r"^/[A-Za-z0-9_./\-]+$")

# Per-command timeout in seconds. Worktree create on a slow disk + cold
# git index can take a while; 60s is enough for normal repos without
# letting a hang block the worker forever.
_GIT_TIMEOUT = 60


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


class WorktreeManager:
    """Wraps `git worktree` operations over a ``CommandExecutor``.

    All methods are idempotent — re-running ``create`` for an existing
    worktree dir or ``remove`` for a missing one is a no-op so retries
    after a partial failure are safe.
    """

    def __init__(self, executor: CommandExecutor, worker_user: str | None = None):
        self._executor = executor
        # When set, the parent ``.worktrees/`` dir is chown'd to this user
        # after creation so the agent (running as the worker user, not
        # root) can write into it. Skip when the executor is local — we
        # don't have a privileged drop pattern there.
        self._worker_user = worker_user

    async def create(self, paths: WorktreePaths) -> None:
        """Ensure the worktree exists and is on the requested branch.

        If the dir already exists we no-op rather than treating that as
        an error: callers re-running ``workspace_setup`` after a transient
        failure should converge, not double-create.
        """
        worktree_dir = paths.worktree_dir
        project_root = paths.project_root
        branch = paths.branch

        # Already created — caller re-running. Nothing to do.
        check_cmd = f"test -d {shlex.quote(worktree_dir)}"
        _, _, rc = await self._executor.run_command(check_cmd, timeout=10)
        if rc == 0:
            logger.info("worktree %s already exists, skipping create", worktree_dir)
            return

        # Make sure ``.worktrees/`` parent exists before git tries to
        # write into it. ``mkdir -p`` is harmless when it already exists.
        parent = f"{project_root}/.worktrees"
        mkdir = f"mkdir -p {shlex.quote(parent)}"
        await self._executor.run_command(mkdir, timeout=10)
        if self._worker_user:
            # Best-effort chown so the agent can write into the parent
            # when ``git worktree add`` runs as the worker user. Failures
            # are non-fatal — let the git step surface a clearer error.
            chown = (
                f"chown {shlex.quote(self._worker_user)}:{shlex.quote(self._worker_user)} "
                f"{shlex.quote(parent)}"
            )
            await self._executor.run_command(chown, timeout=10)

        # ``git -C <root> worktree add -b <branch> <dir>``
        cmd = (
            f"git -C {shlex.quote(project_root)} worktree add "
            f"-b {shlex.quote(branch)} {shlex.quote(worktree_dir)}"
        )
        stdout, stderr, rc = await self._executor.run_command(cmd, timeout=_GIT_TIMEOUT)
        if rc != 0:
            msg = (stderr or stdout or "").lower()
            # Race: another retry created it between our check and add.
            if "already exists" in msg:
                logger.info("worktree %s already created concurrently", worktree_dir)
                return
            raise RuntimeError(
                f"git worktree add failed (rc={rc}): {stderr.strip() or stdout.strip()}"
            )
        logger.info("created worktree %s on branch %s", worktree_dir, branch)

    async def remove(self, paths: WorktreePaths) -> None:
        """Remove the worktree dir + delete the branch.

        Both steps swallow "already gone" errors so a retry after a
        partial failure (or a manual cleanup) doesn't break finalization.
        """
        worktree_dir = paths.worktree_dir
        project_root = paths.project_root
        branch = paths.branch

        rm_cmd = (
            f"git -C {shlex.quote(project_root)} worktree remove "
            f"--force {shlex.quote(worktree_dir)}"
        )
        _, stderr, rc = await self._executor.run_command(rm_cmd, timeout=_GIT_TIMEOUT)
        if rc != 0:
            msg = (stderr or "").lower()
            if "not a working tree" in msg or "no such file" in msg:
                logger.info("worktree %s already gone, skipping remove", worktree_dir)
            else:
                # Don't raise — finalization continues. Log loudly.
                logger.warning(
                    "git worktree remove failed (rc=%d) for %s: %s",
                    rc,
                    worktree_dir,
                    stderr.strip(),
                )

        # Best-effort branch delete. May 404 if the branch was never
        # created (e.g. ``create`` failed before the add) — that's fine.
        br_cmd = f"git -C {shlex.quote(project_root)} branch -D {shlex.quote(branch)}"
        _, br_err, br_rc = await self._executor.run_command(br_cmd, timeout=15)
        if br_rc != 0:
            logger.debug(
                "git branch -D %s failed (rc=%d): %s — likely already gone",
                branch,
                br_rc,
                br_err.strip(),
            )

    async def list(self, project_root: str) -> list[str]:
        """Return absolute paths of all worktrees registered for ``project_root``.

        Used by the orphan-cleanup scheduler. The base repo itself is
        included by ``git worktree list`` — caller filters it out.
        """
        if not _PATH_RE.match(project_root):
            raise ValueError(f"unsafe project_root: {project_root!r}")
        cmd = f"git -C {shlex.quote(project_root)} worktree list --porcelain"
        stdout, stderr, rc = await self._executor.run_command(cmd, timeout=30)
        if rc != 0:
            logger.warning(
                "git worktree list failed (rc=%d) for %s: %s",
                rc,
                project_root,
                stderr.strip(),
            )
            return []
        dirs: list[str] = []
        for line in stdout.splitlines():
            # ``worktree <abs-path>`` is the first record line per entry.
            if line.startswith("worktree "):
                dirs.append(line[len("worktree ") :].strip())
        return dirs

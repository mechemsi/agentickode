# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Remote git operations via SSH — replaces local subprocess git_ops."""

from __future__ import annotations

import logging
import shlex
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.services.workspace.ssh_service import SSHCommandError

if TYPE_CHECKING:
    from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("autodev.remote_git_ops")


class RemoteGitError(RuntimeError):
    """Raised when a remote git command fails."""


@dataclass
class GitResult:
    stdout: str
    stderr: str


class RemoteGitOps:
    """Git operations executed on a remote workspace server via SSH."""

    def __init__(self, ssh: SSHService) -> None:
        self._ssh = ssh

    @property
    def server_label(self) -> str:
        return f"{self._ssh.hostname}:{self._ssh.port}"

    async def run_git(self, args: list[str], cwd: str, timeout: int = 120) -> GitResult:
        """Run a git command on the remote server."""
        quoted_args = " ".join(shlex.quote(a) for a in args)
        cmd = f"cd {shlex.quote(cwd)} && git {quoted_args}"
        label = f"git {' '.join(args)}"
        start = time.monotonic()
        try:
            stdout, stderr, rc = await self._ssh.run_command(cmd, timeout=timeout)
        except SSHCommandError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start
            raise RemoteGitError(
                f"{label} on {self.server_label} failed after {elapsed:.1f}s: {exc}"
            ) from exc
        elapsed = time.monotonic() - start
        if rc != 0:
            raise RemoteGitError(
                f"{label} on {self.server_label} failed (rc={rc}, {elapsed:.1f}s): "
                f"{stderr.strip()[:300]}"
            )
        logger.debug("%s completed in %.1fs", label, elapsed)
        return GitResult(stdout=stdout, stderr=stderr)

    async def has_repo(self, path: str) -> bool:
        """Check if a git repo already exists at the given path."""
        check_cmd = f"test -d {shlex.quote(path)}/.git"
        try:
            _, _, rc = await self._ssh.run_command(check_cmd, timeout=10)
        except SSHCommandError:
            raise
        return rc == 0

    async def _mark_safe_directory(self, path: str) -> None:
        """Add path to git safe.directory to avoid dubious ownership errors."""
        cmd = f"git config --global --add safe.directory {shlex.quote(path)}"
        try:
            await self._ssh.run_command(cmd, timeout=10)
        except Exception:
            logger.debug("Could not set safe.directory for %s (non-fatal)", path)

    async def pull(self, dest: str, branch: str = "main") -> None:
        """Pull latest using the server's own remote config (no URL rewrite)."""
        await self._mark_safe_directory(dest)
        await self._remove_index_lock(dest)
        await self.run_git(["clean", "-fd"], cwd=dest)
        await self.run_git(["reset", "--hard", "HEAD"], cwd=dest)
        await self.run_git(["fetch", "origin"], cwd=dest)
        await self.run_git(["checkout", branch], cwd=dest)
        await self.run_git(["reset", "--hard", f"origin/{branch}"], cwd=dest)

    async def _remove_index_lock(self, path: str) -> None:
        """Remove stale .git/index.lock if present."""
        lock = f"{path}/.git/index.lock"
        cmd = f"rm -f {shlex.quote(lock)}"
        try:
            await self._ssh.run_command(cmd, timeout=10)
        except Exception:
            logger.debug("Could not remove index.lock at %s (non-fatal)", lock)

    async def clone(self, repo_url: str, dest: str, branch: str = "main") -> None:
        """Clone a repo into dest."""
        parent = dest.rsplit("/", 1)[0] if "/" in dest else "."
        await self.mkdir(parent)
        cmd = (
            f"cd {shlex.quote(parent)} && "
            f"git clone --branch {shlex.quote(branch)} "
            f"{shlex.quote(repo_url)} {shlex.quote(dest)}"
        )
        try:
            stdout, stderr, rc = await self._ssh.run_command(cmd, timeout=120)
        except SSHCommandError:
            raise
        if rc != 0:
            raise RemoteGitError(f"git clone on {self.server_label} failed: {stderr.strip()[:300]}")

    async def clone_or_pull(self, repo_url: str, dest: str, branch: str = "main") -> None:
        """Clone a repo if dest doesn't exist, otherwise fetch and reset."""
        await self._mark_safe_directory(dest)
        if await self.has_repo(dest):
            await self.pull(dest, branch=branch)
        else:
            await self.clone(repo_url, dest, branch=branch)

    async def mkdir(self, path: str) -> None:
        """Create a directory (with parents) on the remote server."""
        cmd = f"mkdir -p {shlex.quote(path)}"
        try:
            _, stderr, rc = await self._ssh.run_command(cmd, timeout=10)
        except SSHCommandError:
            raise
        if rc != 0:
            raise RemoteGitError(f"mkdir -p on {self.server_label} failed: {stderr.strip()}")
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""SSH service for connecting to remote workspace servers."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import asyncssh

from backend.config import settings

logger = logging.getLogger("autodev.ssh")

if TYPE_CHECKING:
    from backend.models import WorkspaceServer


class SSHCommandError(RuntimeError):
    """Raised when an SSH command fails with structured context."""

    def __init__(
        self,
        message: str,
        hostname: str = "",
        command: str = "",
        elapsed_s: float = 0,
    ):
        super().__init__(message)
        self.hostname = hostname
        self.command = command
        self.elapsed_s = elapsed_s


@dataclass
class SSHTestResult:
    success: bool
    latency_ms: float | None = None
    error: str | None = None


class SSHService:
    """Async SSH client wrapper for remote server operations."""

    def __init__(
        self,
        hostname: str,
        port: int = 22,
        username: str = "root",
        key_path: str | None = None,
    ):
        self.hostname = hostname
        self.port = port
        self.username = username
        raw = key_path or settings.default_ssh_key_path
        self.key_path = os.path.expanduser(raw)

    @classmethod
    def for_server(cls, server: WorkspaceServer) -> SSHService:
        return cls(
            hostname=server.hostname,
            port=server.port,
            username=server.username,
            key_path=server.ssh_key_path,
        )

    def run_command_as(self, user: str, cmd: str, timeout: int = 30):
        """Run a command as a different user via runuser (login shell). Returns same as run_command."""
        import shlex

        wrapped = f"runuser -l {shlex.quote(user)} -c {shlex.quote(cmd)}"
        return self.run_command(wrapped, timeout=timeout)

    _NON_TRANSIENT_ERRORS = (asyncssh.PermissionDenied,)
    _TRANSIENT_ERRORS = (ConnectionRefusedError, OSError, asyncssh.DisconnectError)
    _MAX_RETRIES = 3
    _BASE_DELAY = 2.0

    async def _connect(self) -> Any:
        return await asyncssh.connect(
            self.hostname,
            port=self.port,
            username=self.username,
            client_keys=[self.key_path],
            known_hosts=None,
        )

    async def _connect_with_retry(self) -> Any:
        """Connect with exponential backoff on transient errors."""
        for attempt in range(self._MAX_RETRIES):
            try:
                return await self._connect()
            except self._NON_TRANSIENT_ERRORS:
                raise
            except self._TRANSIENT_ERRORS as exc:
                if attempt == self._MAX_RETRIES - 1:
                    raise
                delay = self._BASE_DELAY * (2**attempt)
                logger.warning(
                    "SSH connect to %s failed (attempt %d/%d): %s — retrying in %.0fs",
                    self.hostname,
                    attempt + 1,
                    self._MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")  # pragma: no cover

    async def test_connection(self) -> SSHTestResult:
        start = time.monotonic()
        try:
            async with await self._connect() as conn:
                result = await conn.run("echo ok", timeout=10, check=False)
                latency = (time.monotonic() - start) * 1000
                stdout = str(result.stdout or "").strip()
                if stdout == "ok":
                    return SSHTestResult(success=True, latency_ms=round(latency, 1))
                return SSHTestResult(success=False, error=f"Unexpected output: {stdout}")
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return SSHTestResult(success=False, latency_ms=round(latency, 1), error=str(exc))

    async def deploy_key(self, password: str) -> SSHTestResult:
        """Deploy our public key to the remote server via password auth.

        Uses ``client_keys=[]`` to force password-only authentication so
        asyncssh doesn't try (and fail with) key auth before the key is
        deployed.
        """
        pub_path = f"{self.key_path}.pub"
        try:
            with open(pub_path) as f:
                pub_key = f.read().strip()
        except FileNotFoundError:
            return SSHTestResult(success=False, error=f"Public key not found: {pub_path}")

        try:
            async with await asyncssh.connect(
                self.hostname,
                port=self.port,
                username=self.username,
                password=password,
                client_keys=[],  # Disable key auth — force password only
                known_hosts=None,
            ) as conn:
                # Use heredoc-style to avoid shell quoting issues with the key
                cmd = (
                    "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                    f"grep -qxF '{pub_key}' ~/.ssh/authorized_keys 2>/dev/null || "
                    f"printf '%s\\n' '{pub_key}' >> ~/.ssh/authorized_keys ; "
                    "chmod 600 ~/.ssh/authorized_keys"
                )
                result = await conn.run(cmd, timeout=15, check=False)
                if result.returncode != 0:
                    stderr = str(result.stderr or "").strip()
                    return SSHTestResult(
                        success=False,
                        error=f"Failed to deploy key: {stderr}",
                    )
        except asyncssh.PermissionDenied:
            return SSHTestResult(
                success=False,
                error=(
                    f"Password auth denied for {self.username}@{self.hostname}. "
                    "Check: PermitRootLogin yes (if root), "
                    "PasswordAuthentication yes in sshd_config"
                ),
            )
        except Exception as exc:
            return SSHTestResult(success=False, error=str(exc))

        # Verify key-based auth now works
        return await self.test_connection()

    # Paths where user-space installers place binaries (e.g. claude, pipx, npm global).
    # Non-interactive SSH doesn't source .bashrc, so we prepend these explicitly.
    _EXTRA_PATH = (
        "$HOME/.local/bin:$HOME/.claude/bin:$HOME/go/bin" ":$HOME/.cargo/bin:$HOME/.npm-global/bin"
    )

    async def run_command(self, cmd: str, timeout: int = 30) -> tuple[str, str, int]:
        """Run a command via SSH. Returns (stdout, stderr, exit_code)."""
        wrapped = f'export PATH="{self._EXTRA_PATH}:$PATH" && {cmd}'
        start = time.monotonic()
        try:
            conn = await asyncio.wait_for(self._connect_with_retry(), timeout=min(timeout, 15))
        except TimeoutError:
            elapsed = time.monotonic() - start
            raise SSHCommandError(
                f"SSH connect to {self.hostname}:{self.port} timed out after {elapsed:.1f}s",
                hostname=self.hostname,
                command=cmd,
                elapsed_s=round(elapsed, 1),
            ) from None
        except OSError as exc:
            elapsed = time.monotonic() - start
            raise SSHCommandError(
                f"SSH connect to {self.hostname}:{self.port} failed: {exc}",
                hostname=self.hostname,
                command=cmd,
                elapsed_s=round(elapsed, 1),
            ) from exc

        try:
            async with conn:
                result = await asyncio.wait_for(
                    conn.run(wrapped, timeout=timeout, check=False),
                    timeout=timeout + 5,
                )
                return (
                    str(result.stdout or ""),
                    str(result.stderr or ""),
                    result.returncode if result.returncode is not None else 0,
                )
        except TimeoutError:
            elapsed = time.monotonic() - start
            raise SSHCommandError(
                f"SSH command timed out after {elapsed:.1f}s on {self.hostname}: {cmd[:120]}",
                hostname=self.hostname,
                command=cmd,
                elapsed_s=round(elapsed, 1),
            ) from None

    async def run_command_stream(self, cmd: str, timeout: int = 300) -> AsyncIterator[str]:
        """Run a command via SSH, yielding stdout lines as they arrive."""
        wrapped = f'export PATH="{self._EXTRA_PATH}:$PATH" && {cmd}'
        conn = await asyncio.wait_for(self._connect_with_retry(), timeout=min(timeout, 15))
        try:
            async with conn:
                process = await conn.create_process(wrapped)
                assert process.stdout is not None
                try:
                    async with asyncio.timeout(timeout):
                        async for line in process.stdout:
                            yield str(line).rstrip("\n")
                except TimeoutError:
                    process.kill()
                    yield "[timed out]"
                await process.wait()
                rc = process.returncode or 0
                yield f"\n[exit code: {rc}]"
        except Exception as exc:
            yield f"[error: {exc}]"
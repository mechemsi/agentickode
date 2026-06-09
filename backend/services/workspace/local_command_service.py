# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Local command executor — runs commands via subprocess on the platform container."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import time
from collections.abc import AsyncIterator

from backend.services.workspace.ssh_service import SSHTestResult

logger = logging.getLogger("agentickode.local_cmd")

# Same extra PATH as SSHService so agents installed in user-space are found.
_EXTRA_PATH = (
    "$HOME/.local/bin:$HOME/.claude/bin:$HOME/go/bin" ":$HOME/.cargo/bin:$HOME/.npm-global/bin"
)


class LocalCommandService:
    """Execute commands locally via asyncio subprocess (no SSH)."""

    def __init__(self) -> None:
        self.hostname = "localhost"
        self.port = 0  # parity with SSHService (no real port for local execution)
        self.username = os.environ.get("USER", "root")

    async def run_command(self, cmd: str, timeout: int = 30) -> tuple[str, str, int]:
        """Run a command locally. Returns (stdout, stderr, exit_code)."""
        wrapped = f'export PATH="{_EXTRA_PATH}:$PATH" && {cmd}'
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_shell(
                wrapped,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return (
                stdout_bytes.decode(errors="replace"),
                stderr_bytes.decode(errors="replace"),
                proc.returncode or 0,
            )
        except TimeoutError:
            elapsed = time.monotonic() - start
            logger.error("Local command timed out after %.1fs: %s", elapsed, cmd[:120])
            raise RuntimeError(
                f"Local command timed out after {elapsed:.1f}s: {cmd[:120]}"
            ) from None

    def run_command_as(self, user: str, cmd: str, timeout: int = 30):
        """Run a command as a different user via runuser."""
        wrapped = f"runuser -l {shlex.quote(user)} -c {shlex.quote(cmd)}"
        return self.run_command(wrapped, timeout=timeout)

    async def run_command_stream(self, cmd: str, timeout: int = 300) -> AsyncIterator[str]:
        """Run a command locally, yielding stdout lines as they arrive."""
        wrapped = f'export PATH="{_EXTRA_PATH}:$PATH" && {cmd}'
        proc = await asyncio.create_subprocess_shell(
            wrapped,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        try:
            async with asyncio.timeout(timeout):
                async for raw_line in proc.stdout:
                    yield raw_line.decode(errors="replace").rstrip("\n")
        except TimeoutError:
            proc.kill()
            yield "[timed out]"
        await proc.wait()
        rc = proc.returncode or 0
        yield f"\n[exit code: {rc}]"

    async def fire_and_forget(self, cmd: str, timeout: int = 15) -> None:
        """Start a background command without waiting for completion."""
        wrapped = f'export PATH="{_EXTRA_PATH}:$PATH" && {cmd}'
        detach_cmd = (
            f"bash -c 'nohup setsid bash -c {shlex.quote(wrapped)} "
            f"</dev/null >/dev/null 2>&1 & exit 0'"
        )
        proc = await asyncio.create_subprocess_shell(
            detach_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except TimeoutError:
            logger.warning(
                "fire_and_forget timed out after %ds (process may still be running): %s",
                timeout,
                cmd[:120],
            )

    async def test_connection(self) -> SSHTestResult:
        """Local connection always succeeds."""
        start = time.monotonic()
        try:
            stdout, _, rc = await self.run_command("echo ok", timeout=5)
            latency = (time.monotonic() - start) * 1000
            if stdout.strip() == "ok" and rc == 0:
                return SSHTestResult(success=True, latency_ms=round(latency, 1))
            return SSHTestResult(success=False, error=f"Unexpected: {stdout.strip()}")
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return SSHTestResult(success=False, latency_ms=round(latency, 1), error=str(exc))

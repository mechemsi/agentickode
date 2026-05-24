# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""HostBridgeService — CommandExecutor that talks to the host bridge daemon.

When the local platform server is configured with a ``bridge_url`` and
``bridge_token`` (see migration 039), all commands the backend would
normally run in-container are forwarded to ``scripts/host_bridge.py``
running on the host instead. The host process uses the host's user,
PATH, and filesystem — chat / terminal / workflow steps then execute
against the operator's actual host environment.

Implements the same Protocol as ``LocalCommandService`` /
``SSHService`` so it plugs into ``executor_for_server`` without further
plumbing.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from backend.services.workspace.ssh_service import SSHTestResult

logger = logging.getLogger("agentickode.host_bridge_service")


def _normalize_url(url: str) -> str:
    """Strip trailing slash so we can append ``/path`` freely."""
    return url.rstrip("/")


class HostBridgeService:
    """Routes CommandExecutor calls through the host bridge daemon."""

    def __init__(self, bridge_url: str, token: str):
        if not bridge_url or not token:
            raise ValueError("host bridge requires both bridge_url and token")
        self._url = _normalize_url(bridge_url)
        self._token = token
        # ``hostname``/``username`` are surfaced for log messages and
        # for code paths that key off ``ssh.username == "root"``. The
        # bridge runs as the operator's host user, so claim that here.
        self.hostname = self._url
        # We don't know the real host username until we ping /health.
        # Default to a sentinel so any ``== "root"`` checks naturally
        # treat us like a non-root SSH user (skip privilege-drop wrap).
        self.username = "host-bridge"

    @property
    def port(self) -> int:
        """Provided for log-format compatibility with SSH services."""
        return 0

    # ── HTTP helper ──────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _post_run(
        self,
        cmd: str,
        *,
        timeout: int,
        stdin: str | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str, int]:
        # ``timeout`` controls the host-side subprocess timeout. Add a
        # small slack to the HTTP-client timeout so the daemon's own
        # 504 reaches us cleanly instead of an httpx ReadTimeout.
        body: dict[str, object] = {"cmd": cmd, "timeout": timeout}
        if stdin is not None:
            body["stdin"] = stdin
        if env:
            body["env"] = env
        async with httpx.AsyncClient(timeout=timeout + 15) as client:
            resp = await client.post(f"{self._url}/run", headers=self._headers(), json=body)
        if resp.status_code == 401:
            raise PermissionError("host bridge rejected bearer token")
        if resp.status_code >= 500:
            raise RuntimeError(f"host bridge {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return data.get("stdout", ""), data.get("stderr", ""), int(data.get("exit_code", 1))

    async def write_tempfile(self, content: str, *, suffix: str = "") -> str:
        """Drop ``content`` into a host-side temp file; return the path.

        Chat uses this so Claude can read its MCP config from a real
        host path (``claude --mcp-config <path>`` requires a file).
        """
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._url}/write_tempfile",
                headers=self._headers(),
                json={"content": content, "suffix": suffix},
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"host bridge write_tempfile failed: {resp.status_code} {resp.text[:200]}"
            )
        return resp.json()["path"]

    async def run_command_with_stdin(
        self,
        cmd: str,
        stdin: str,
        *,
        timeout: int = 600,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str, int]:
        """Run ``cmd`` and pipe ``stdin`` to it. Used by chat to feed
        the user message to ``claude -p`` without a shared /tmp."""
        return await self._post_run(cmd, timeout=timeout, stdin=stdin, env=env)

    # ── CommandExecutor protocol ─────────────────────────────────

    async def run_command(self, cmd: str, timeout: int = 30) -> tuple[str, str, int]:
        return await self._post_run(cmd, timeout=timeout)

    async def run_command_as(self, user: str, cmd: str, timeout: int = 30) -> tuple[str, str, int]:
        # The bridge already runs as the operator's host user. If a
        # caller asks for a *different* user, we wrap with sudo so
        # the operator's passwordless-sudo policy (if any) decides
        # whether it's allowed. Without sudo this falls through with
        # rc != 0 — clearer than silently running as the wrong user.
        import shlex

        wrapped = f"sudo -u {shlex.quote(user)} -- bash -lc {shlex.quote(cmd)}"
        return await self._post_run(wrapped, timeout=timeout)

    async def run_command_stream(self, cmd: str, timeout: int = 300) -> AsyncIterator[str]:
        # Minimal streaming: just call the synchronous run and yield
        # stdout as one chunk. Real line-by-line streaming over a
        # second WebSocket endpoint is a follow-up; the workflow
        # pipeline mostly uses run_command, not the stream.
        stdout, _, _ = await self._post_run(cmd, timeout=timeout)
        if stdout:
            yield stdout

    async def fire_and_forget(self, cmd: str, timeout: int = 15) -> None:
        # No real "fire and forget" channel — call /run and ignore the
        # result. Bridge will keep running synchronously; this is fine
        # for the only caller (cleanup helpers).
        try:
            await self._post_run(cmd, timeout=timeout)
        except Exception:
            logger.debug("fire_and_forget swallowed exception", exc_info=True)

    async def test_connection(self) -> SSHTestResult:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._url}/health")
            if resp.status_code != 200:
                return SSHTestResult(success=False, error=f"HTTP {resp.status_code}")
            data = resp.json()
            self.username = data.get("user") or self.username
            return SSHTestResult(success=True, latency_ms=0.0)
        except httpx.HTTPError as exc:
            return SSHTestResult(success=False, error=str(exc))


def host_bridge_from_server(server) -> HostBridgeService | None:
    """Return a HostBridgeService for ``server`` if it's configured.

    ``server`` is a ``WorkspaceServer`` row. We decrypt the token here
    so callers don't have to know about ``services.encryption``.
    """
    from backend.services.encryption import decrypt_value

    url = getattr(server, "bridge_url", None)
    token_enc = getattr(server, "bridge_token_enc", None)
    if not url or not token_enc:
        return None
    try:
        token = decrypt_value(token_enc)
    except Exception:
        logger.warning(
            "bridge_token_enc for server %s failed to decrypt; ignoring",
            getattr(server, "id", "?"),
        )
        return None
    return HostBridgeService(url, token)

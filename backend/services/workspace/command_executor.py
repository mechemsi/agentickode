# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CommandExecutor protocol — unified interface for local and SSH execution."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from backend.services.workspace.ssh_service import SSHService, SSHTestResult

if TYPE_CHECKING:
    from backend.models import WorkspaceServer


@runtime_checkable
class CommandExecutor(Protocol):
    """Protocol for running commands on a workspace server (local or remote)."""

    hostname: str
    username: str

    async def run_command(self, cmd: str, timeout: int = 30) -> tuple[str, str, int]:
        """Run a command. Returns (stdout, stderr, exit_code)."""
        ...

    def run_command_as(
        self, user: str, cmd: str, timeout: int = 30
    ) -> AsyncIterator[tuple[str, str, int]] | object:
        """Run a command as a different user. Returns awaitable of (stdout, stderr, exit_code)."""
        ...

    async def run_command_stream(self, cmd: str, timeout: int = 300) -> AsyncIterator[str]:
        """Run a command, yielding stdout lines as they arrive."""
        ...
        yield ""  # pragma: no cover

    async def fire_and_forget(self, cmd: str, timeout: int = 15) -> None:
        """Start a command without waiting for it to finish."""
        ...

    async def test_connection(self) -> SSHTestResult:
        """Test connectivity. Returns SSHTestResult."""
        ...


def executor_for_server(server: WorkspaceServer) -> CommandExecutor:
    """Factory: pick the right executor for a workspace server.

    Dispatch order:
    1. ``server_type == "local"`` with ``bridge_url`` + ``bridge_token_enc``
       configured → ``HostBridgeService``. Commands run on the operator's
       host via ``scripts/host_bridge.py``.
    2. ``server_type == "local"`` without a bridge → ``LocalCommandService``
       (legacy: commands run in the backend container itself).
    3. Anything else → ``SSHService`` to a remote workspace server.
    """
    if getattr(server, "server_type", "remote") == "local":
        # Prefer host bridge when configured.
        from backend.services.workspace.host_bridge_service import (
            host_bridge_from_server,
        )

        bridge = host_bridge_from_server(server)
        if bridge is not None:
            return bridge

        from backend.services.workspace.local_command_service import LocalCommandService

        return LocalCommandService()
    return SSHService.for_server(server)

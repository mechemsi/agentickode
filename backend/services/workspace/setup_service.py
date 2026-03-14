# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Async server setup orchestrator — runs after a workspace server is added."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.services.workspace._setup_steps import execute_step

logger = logging.getLogger("agentickode.server_setup")

SETUP_STEPS = [
    "ssh_test",
    "install_system_deps",
    "create_worker_user",
    "create_workspace_dir",
    "install_agents",
    "sync_agents",
    "generate_ssh_key",
    "discover",
    "mark_online",
]


def _step_entry(status: str = "pending", error: str | None = None) -> dict[str, Any]:
    return {"status": status, "error": error, "timestamp": datetime.now(UTC).isoformat()}


def _get_setup_log(server: Any) -> dict[str, Any]:
    raw = server.setup_log
    return dict(raw) if raw else {}  # type: ignore[arg-type]


class ServerSetupService:
    """Orchestrates async server setup after creation."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    def kick_off_setup(
        self, server_id: int, *, setup_password: str | None = None
    ) -> asyncio.Task[None]:
        """Launch async setup in background, returns the task handle."""
        return asyncio.create_task(self._run_setup(server_id, setup_password=setup_password))

    async def retry_setup(self, server_id: int) -> None:
        """Re-run setup from the first failed step."""
        await self._run_setup(server_id, retry=True)

    async def _run_setup(
        self, server_id: int, *, retry: bool = False, setup_password: str | None = None
    ) -> None:
        try:
            async with self._session_factory() as session:
                repo = WorkspaceServerRepository(session)
                server = await repo.get_by_id(server_id)
                if not server:
                    logger.error("Server %d not found for setup", server_id)
                    return

                # Initialize or resume setup_log
                setup_log: dict[str, Any] = _get_setup_log(server)
                if not retry:
                    setup_log = {step: _step_entry() for step in SETUP_STEPS}
                start_from = self._find_resume_step(setup_log) if retry else 0

                await repo.update(
                    server,
                    {"status": "setting_up", "setup_log": setup_log, "error_message": None},
                )

            # Run each step
            for i, step_name in enumerate(SETUP_STEPS):
                if i < start_from:
                    continue
                try:
                    async with self._session_factory() as session:
                        repo = WorkspaceServerRepository(session)
                        server = await repo.get_by_id(server_id)
                        if not server:
                            return
                        setup_log = _get_setup_log(server)
                        setup_log[step_name] = _step_entry("running")
                        await repo.update(server, {"setup_log": setup_log})

                    await execute_step(
                        self._session_factory,
                        server_id,
                        step_name,
                        setup_password=setup_password,
                    )

                    async with self._session_factory() as session:
                        repo = WorkspaceServerRepository(session)
                        server = await repo.get_by_id(server_id)
                        if not server:
                            return
                        setup_log = _get_setup_log(server)
                        setup_log[step_name] = _step_entry("completed")
                        await repo.update(server, {"setup_log": setup_log})

                except Exception as exc:
                    logger.exception("Setup step %s failed for server %d", step_name, server_id)
                    async with self._session_factory() as session:
                        repo = WorkspaceServerRepository(session)
                        server = await repo.get_by_id(server_id)
                        if not server:
                            return
                        setup_log = _get_setup_log(server)
                        setup_log[step_name] = _step_entry("failed", str(exc))
                        await repo.update(
                            server,
                            {
                                "status": "setup_failed",
                                "error_message": f"Step '{step_name}' failed: {exc}",
                                "setup_log": setup_log,
                            },
                        )
                    return

        except Exception:
            logger.exception("Unexpected error during setup for server %d", server_id)

    @staticmethod
    def _find_resume_step(setup_log: dict[str, Any]) -> int:
        """Find the index of the first non-completed step."""
        for i, step in enumerate(SETUP_STEPS):
            entry = setup_log.get(step, {})
            if entry.get("status") != "completed":
                return i
        return len(SETUP_STEPS)

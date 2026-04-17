# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Append-only event log for autonomous agent execution.

Writes structured events to ``.autodev/event_log.jsonl`` on the remote
workspace server for audit, debugging, and recovery purposes.
"""

from __future__ import annotations

import json
import logging
import shlex
from datetime import UTC, datetime

from backend.services.workspace.command_executor import CommandExecutor

logger = logging.getLogger("agentickode.event_log")


class EventLog:
    """Append-only execution event log stored on the remote workspace."""

    def __init__(self, ssh: CommandExecutor, workspace: str):
        self._ssh = ssh
        self._workspace = workspace
        self._path = f"{workspace}/.autodev/event_log.jsonl"

    async def append(self, event_type: str, data: dict | None = None) -> None:
        """Append an event to the log file.

        Args:
            event_type: One of: episode_started, episode_completed,
                git_checkpoint, stall_detected, recovery_started,
                context_compacted, agent_killed.
            data: Additional event-specific data.
        """
        event = {
            "type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            **(data or {}),
        }
        line = json.dumps(event, separators=(",", ":"))
        escaped = line.replace("'", "'\\''")
        await self._ssh.run_command(
            f"echo '{escaped}' >> {shlex.quote(self._path)}",
            timeout=10,
        )

    async def read_all(self) -> list[dict]:
        """Read all events from the log file."""
        stdout, _, rc = await self._ssh.run_command(
            f"cat {shlex.quote(self._path)} 2>/dev/null",
            timeout=15,
        )
        if rc != 0 or not stdout.strip():
            return []

        events: list[dict] = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    events.append(event)
            except json.JSONDecodeError:
                continue
        return events

    async def read_since(self, after_line: int) -> list[dict]:
        """Read events after a given line number (1-based)."""
        stdout, _, rc = await self._ssh.run_command(
            f"tail -n +{after_line + 1} {shlex.quote(self._path)} 2>/dev/null",
            timeout=15,
        )
        if rc != 0 or not stdout.strip():
            return []

        events: list[dict] = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    events.append(event)
            except json.JSONDecodeError:
                continue
        return events

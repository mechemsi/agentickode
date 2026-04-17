# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Session recovery — detects and recovers dead autonomous agent sessions.

Checks if the remote agent process is still alive, and if not, restores
the workspace from the last git checkpoint and builds a recovery context
for the next episode.
"""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass

from backend.models.episodes import Episode
from backend.services.context_compactor import ContextCompactor
from backend.services.workspace.command_executor import CommandExecutor

logger = logging.getLogger("agentickode.session_recovery")


@dataclass
class RecoveryContext:
    """Context needed to resume execution after a crash."""

    session_id: str
    summary: str
    last_episode_num: int
    checkpoint_sha: str | None


class SessionRecoveryService:
    """Detect dead sessions and recover from git checkpoints."""

    def __init__(self, ssh: CommandExecutor, workspace: str):
        self._ssh = ssh
        self._workspace = workspace

    async def is_agent_alive(self, episode_num: int) -> bool:
        """Check if the agent process is still running.

        Looks for the exit code file (means process finished) or checks
        if a claude process is active for this workspace.
        """
        ws = shlex.quote(self._workspace)

        # If exit code file exists, the process finished (alive=False in running sense)
        exit_path = f"{ws}/.autodev/episode_{episode_num}_exit_code"
        stdout, _, rc = await self._ssh.run_command(
            f"cat {exit_path} 2>/dev/null",
            timeout=10,
        )
        if rc == 0 and stdout.strip():
            return False  # Process finished

        # Check if claude process is running for this workspace
        stdout, _, rc = await self._ssh.run_command(
            f"pgrep -f 'claude.*{ws}' 2>/dev/null | head -1",
            timeout=10,
        )
        return rc == 0 and bool(stdout.strip())

    async def recover(
        self,
        last_episode: Episode,
        session_id: str,
    ) -> RecoveryContext:
        """Recover from a dead session.

        1. Reset workspace to last checkpoint if dirty
        2. Build compacted context summary
        3. Return RecoveryContext for the next episode
        """
        ws = shlex.quote(self._workspace)
        checkpoint_sha = last_episode.git_checkpoint_sha

        # Reset to last checkpoint if we have one and workspace is dirty
        if checkpoint_sha:
            dirty_out, _, _ = await self._ssh.run_command(
                f"cd {ws} && git status --porcelain 2>/dev/null | head -1",
                timeout=15,
            )
            if dirty_out.strip():
                logger.info("Resetting workspace to checkpoint %s", checkpoint_sha[:8])
                await self._ssh.run_command(
                    f"cd {ws} && git checkout -- . && git clean -fd 2>/dev/null",
                    timeout=30,
                )

        # Build compacted summary from last episode
        compactor = ContextCompactor(self._ssh, self._workspace)
        summary = last_episode.summary or ""
        if not summary:
            summary = await compactor.compact_episode(last_episode.episode_number)

        return RecoveryContext(
            session_id=session_id,
            summary=summary,
            last_episode_num=last_episode.episode_number,
            checkpoint_sha=checkpoint_sha,
        )

    async def check_for_orphaned_process(self) -> bool:
        """Check if there's an orphaned claude process for this workspace."""
        ws = shlex.quote(self._workspace)
        stdout, _, rc = await self._ssh.run_command(
            f"pgrep -f 'claude.*{ws}' 2>/dev/null | wc -l",
            timeout=10,
        )
        try:
            count = int(stdout.strip())
            return count > 0
        except ValueError:
            return False

    async def kill_orphaned_process(self) -> None:
        """Kill any orphaned claude processes for this workspace."""
        ws = shlex.quote(self._workspace)
        await self._ssh.run_command(
            f"pkill -f 'claude.*{ws}' 2>/dev/null || true",
            timeout=10,
        )
        logger.info("Killed orphaned claude processes for %s", self._workspace)

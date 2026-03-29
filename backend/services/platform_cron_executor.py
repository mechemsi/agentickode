# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Execute platform crons — send prompts to local agent terminal sessions."""

import asyncio
import logging
import os
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.local_sessions import LocalTerminalSession
from backend.models.platform_crons import PlatformCron

logger = logging.getLogger("agentickode.platform_cron_executor")

_ENV = {
    **os.environ,
    "TERM": "xterm-256color",
    "PATH": f"/root/.local/bin:/root/.local/share/claude/bin:{os.environ.get('PATH', '')}",
}


class PlatformCronExecutor:
    """Send prompts to local agent sessions when crons fire."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def execute_cron(self, cron: PlatformCron) -> str:
        """Execute a single cron. Returns result status."""
        tmux_name = await self._resolve_session(cron)
        if not tmux_name:
            return await self._record(cron, "session_not_found")

        # Check tmux exists
        if not await self._tmux_exists(tmux_name):
            # Try to auto-resume the session
            resumed = await self._auto_resume(cron)
            if not resumed:
                return await self._record(cron, "session_dead")
            tmux_name = resumed

        # Send prompt to session
        escaped = cron.prompt.replace("'", "'\\''")
        proc = await asyncio.create_subprocess_shell(
            f"tmux send-keys -t {tmux_name} '{escaped}' Enter",
            env=_ENV,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        if proc.returncode != 0:
            stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
            logger.error("Cron %d: send failed: %s", cron.id, stderr)
            return await self._record(cron, "send_error")

        logger.info("Cron %d: sent prompt to %s", cron.id, tmux_name)
        return await self._record(cron, "success")

    async def _resolve_session(self, cron: PlatformCron) -> str | None:
        """Get tmux_name from session_id, or find any active session for agent."""
        if cron.session_id:
            result = await self._db.execute(
                select(LocalTerminalSession).where(
                    LocalTerminalSession.session_id == cron.session_id
                )
            )
            session = result.scalar_one_or_none()
            if session:
                return str(session.tmux_name)

        # Fallback: find any active session for this agent
        result = await self._db.execute(
            select(LocalTerminalSession)
            .where(
                LocalTerminalSession.agent_name == cron.agent_name,
                LocalTerminalSession.status == "active",
            )
            .order_by(LocalTerminalSession.last_activity_at.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()
        return str(session.tmux_name) if session else None

    async def _auto_resume(self, cron: PlatformCron) -> str | None:
        """Auto-resume a closed session or create a new one."""
        # Try to resume the linked session
        if cron.session_id:
            result = await self._db.execute(
                select(LocalTerminalSession).where(
                    LocalTerminalSession.session_id == cron.session_id
                )
            )
            session = result.scalar_one_or_none()
            if session:
                return await self._resume_session(session)

        # Create a brand new session
        return await self._create_session(cron)

    async def _resume_session(self, session: LocalTerminalSession) -> str | None:
        """Re-create tmux for a closed session."""
        proc = await asyncio.create_subprocess_shell(
            f"tmux new-session -d -s {session.tmux_name} -x 120 -y 40",
            env=_ENV,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        if proc.returncode != 0:
            return None

        if session.agent_session_id and session.agent_name == "claude":
            agent_cmd = f"claude --permission-mode auto --resume {session.agent_session_id}"
        else:
            agent_cmd = session.last_command or str(session.agent_name)
        await asyncio.create_subprocess_shell(
            f"tmux send-keys -t {session.tmux_name} '{agent_cmd}' Enter",
            env=_ENV,
        )
        # Wait for agent to start
        await asyncio.sleep(3)

        session.status = "active"
        session.closed_at = None
        session.last_activity_at = datetime.now(UTC)
        logger.info("Auto-resumed session %s for cron", session.tmux_name)
        return str(session.tmux_name)

    async def _create_session(self, cron: PlatformCron) -> str | None:
        """Create a new session for a cron that has no linked session."""
        import uuid

        session_id = uuid.uuid4().hex[:12]
        tmux_name = f"lt-{cron.agent_name}-{session_id}"

        agent_cmd = (
            "claude --permission-mode auto" if cron.agent_name == "claude" else cron.agent_name
        )

        proc = await asyncio.create_subprocess_shell(
            f"tmux new-session -d -s {tmux_name} -x 120 -y 40",
            env=_ENV,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        if proc.returncode != 0:
            return None

        await asyncio.create_subprocess_shell(
            f"tmux send-keys -t {tmux_name} '{agent_cmd}' Enter",
            env=_ENV,
        )
        await asyncio.sleep(3)

        session = LocalTerminalSession(
            session_id=session_id,
            agent_name=cron.agent_name,
            tmux_name=tmux_name,
            display_name=f"[cron] {cron.name}",
            last_command=agent_cmd,
            status="active",
        )
        self._db.add(session)

        # Link cron to this new session
        cron.session_id = session_id
        logger.info("Created session %s for cron %d", tmux_name, cron.id)
        return tmux_name

    async def _record(self, cron: PlatformCron, result: str) -> str:
        """Record execution result."""
        now = datetime.now(UTC)
        cron.last_run_at = now
        cron.last_result = result
        cron.run_count = (cron.run_count or 0) + 1

        # Append to execution log (keep last 50)
        log = list(cron.execution_log or [])
        log.append({"at": now.isoformat(), "result": result})
        cron.execution_log = log[-50:]

        return result

    @staticmethod
    async def _tmux_exists(tmux_name: str) -> bool:
        proc = await asyncio.create_subprocess_shell(
            f"tmux has-session -t {tmux_name} 2>/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        return proc.returncode == 0

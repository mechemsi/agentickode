# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Execute parsed commands using platform services."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.runs import TaskRun
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.services.messaging.command_parser import Command
from backend.services.run_factory import create_task_run

logger = logging.getLogger("agentickode.messaging.executor")

_HELP_TEXT = (
    "*AgenticKode Commands:*\n"
    "`run <project> <task>` — Create a new run\n"
    "`status [run_id]` — Check run status\n"
    "`approve <run_id>` — Approve a pending run\n"
    "`reject <run_id> [reason]` — Reject a pending run\n"
    "`list` — List recent runs\n"
    "`talk <session_id> <message>` — Send message to running agent\n"
    "`help` — Show this help"
)


class CommandExecutor:
    """Execute messaging commands against platform services."""

    async def execute(self, cmd: Command, session: AsyncSession) -> str:
        """Execute a command and return a response message."""
        if cmd.action == "help":
            return _HELP_TEXT
        if cmd.action == "run":
            return await self._cmd_run(cmd, session)
        if cmd.action == "status":
            return await self._cmd_status(cmd, session)
        if cmd.action == "approve":
            return await self._cmd_approve(cmd, session)
        if cmd.action == "reject":
            return await self._cmd_reject(cmd, session)
        if cmd.action == "list":
            return await self._cmd_list(session)
        return _HELP_TEXT

    async def _cmd_run(self, cmd: Command, session: AsyncSession) -> str:
        if not cmd.project:
            return "Usage: `run <project> <task description>`"

        repo = ProjectConfigRepository(session)
        project = await repo.get_by_id(cmd.project)
        if not project:
            return f"Project `{cmd.project}` not found."

        task = cmd.args.get("task", "Task from messaging")
        task_id = f"msg-{uuid.uuid4().hex[:8]}"
        run = create_task_run(
            task_id=task_id,
            project=project,
            title=task[:200],
            description=task,
            task_source="messaging",
            task_source_meta={"channel": "slack/discord", "raw_command": cmd.raw_text},
        )
        session.add(run)
        await session.flush()
        return f"Created run *#{run.id}* for `{cmd.project}`: {task[:100]}"

    async def _cmd_status(self, cmd: Command, session: AsyncSession) -> str:
        run_id = cmd.args.get("run_id", "")
        if not run_id or not run_id.isdigit():
            return "Usage: `status <run_id>`"

        result = await session.execute(select(TaskRun).where(TaskRun.id == int(run_id)))
        run = result.scalar_one_or_none()
        if not run:
            return f"Run #{run_id} not found."

        status = run.status or "unknown"
        phase = run.current_phase or "-"
        return f"*Run #{run_id}*: {status} (phase: {phase})"

    async def _cmd_approve(self, cmd: Command, session: AsyncSession) -> str:
        run_id = cmd.args.get("run_id", "")
        if not run_id or not run_id.isdigit():
            return "Usage: `approve <run_id>`"

        result = await session.execute(select(TaskRun).where(TaskRun.id == int(run_id)))
        run = result.scalar_one_or_none()
        if not run:
            return f"Run #{run_id} not found."
        if run.status != "awaiting_approval":
            return f"Run #{run_id} is not awaiting approval (status: {run.status})."

        run.approved = True
        return f"Run #{run_id} approved."

    async def _cmd_reject(self, cmd: Command, session: AsyncSession) -> str:
        run_id = cmd.args.get("run_id", "")
        if not run_id or not run_id.isdigit():
            return "Usage: `reject <run_id> [reason]`"

        result = await session.execute(select(TaskRun).where(TaskRun.id == int(run_id)))
        run = result.scalar_one_or_none()
        if not run:
            return f"Run #{run_id} not found."

        run.approved = False
        run.rejection_reason = cmd.args.get("reason", "Rejected via messaging")
        return f"Run #{run_id} rejected."

    async def _cmd_list(self, session: AsyncSession) -> str:
        result = await session.execute(select(TaskRun).order_by(TaskRun.id.desc()).limit(5))
        runs = result.scalars().all()
        if not runs:
            return "No runs found."

        lines = ["*Recent runs:*"]
        for run in runs:
            lines.append(f"• #{run.id} `{run.status}` — {run.title[:60]}")
        return "\n".join(lines)

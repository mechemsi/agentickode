# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Autonomous agent loop phase.

Replaces the planning → coding → testing → reviewing sequence with a single
phase where Claude Code drives itself end-to-end with full tool access.

The agent:
  1. Reads .autodev/context.md for project context
  2. Creates its own plan
  3. Executes — writes code, runs tests, self-reviews
  4. Writes .autodev/result.json on completion
  5. Optionally writes .autodev/follow_up_tasks.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentLoopExecution, TaskRun
from backend.services.container import ServiceContainer
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._context_builder import (
    build_context_package,
    read_workspace_json,
)
from backend.worker.phases._followup_handler import process_followup_tasks
from backend.worker.phases._helpers import get_ssh_for_run

logger = logging.getLogger("agentickode.phases.agent_loop")

PHASE_META = {
    "name": "agent_loop",
    "description": "Autonomous agent loop — Claude Code drives exploration, planning, and execution",
    "default_role": None,
    "default_agent_mode": "task",
}

# How often (seconds) to poll .autodev/progress.json for UI updates
_POLL_INTERVAL = 5

# Default timeout for the agent loop (seconds) — 90 minutes
_DEFAULT_TIMEOUT = 5400

# How long to wait for plan.json before timing out (seconds)
_PLAN_POLL_TIMEOUT = 300


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> dict | None:
    """Execute the autonomous agent loop."""
    await broadcaster.log(task_run.id, "Starting autonomous agent loop", phase="agent_loop")

    # Load project autonomy_config
    autonomy_config = await _load_autonomy_config(task_run, session)
    plan_approval = autonomy_config.get("plan_approval", "none")
    timeout = int(autonomy_config.get("agent_timeout_seconds", _DEFAULT_TIMEOUT))

    # 1. Build context package in workspace
    await broadcaster.log(task_run.id, "Building context package for agent", phase="agent_loop")
    session_id = await build_context_package(
        task_run, session, services, autonomy_config=autonomy_config
    )

    # 2. Create AgentLoopExecution tracking record
    loop_exec = AgentLoopExecution(
        task_run_id=task_run.id,
        started_at=datetime.now(UTC),
        session_id=session_id,
        status="running",
    )
    session.add(loop_exec)
    await session.commit()

    ssh = await get_ssh_for_run(task_run, session)
    workspace = task_run.workspace_path or ""

    # 3. Start the Claude autonomous invocation (non-blocking via SSH background task)
    claude_cmd = (
        f"cd {shlex.quote(workspace)} && "
        f"claude --dangerously-skip-permissions --print --output-format stream-json "
        f"< .autodev/agent_prompt.md "
        f"> .autodev/claude_output.jsonl 2>.autodev/claude_stderr.log; "
        f"echo $? > .autodev/claude_exit_code"
    )

    await broadcaster.log(task_run.id, "Launching Claude Code autonomous agent", phase="agent_loop")
    _, _, launch_rc = await ssh.run_command(
        f"nohup bash -c {shlex.quote(claude_cmd)} &",
        timeout=10,
    )
    if launch_rc not in (0, 1):  # nohup returns 0 or 1 depending on shell
        logger.warning("nohup launch returned rc=%s for run #%s", launch_rc, task_run.id)

    # 4. Handle plan approval gate
    if plan_approval in ("require_approval", "show_and_continue"):
        result = await _wait_for_plan(task_run, session, ssh, workspace, plan_approval)
        if result == "awaiting_plan_approval":
            loop_exec.status = "waiting_plan"
            await session.commit()
            return result  # type: ignore[return-value]

    # 5. Poll for progress and completion
    result_data = await _poll_until_done(
        task_run=task_run,
        session=session,
        ssh=ssh,
        workspace=workspace,
        loop_exec=loop_exec,
        timeout=timeout,
    )

    # 6. Store results on task_run
    if result_data:
        task_run.coding_results = result_data
        plan_data = await read_workspace_json(ssh, workspace, ".autodev/plan.json")
        if plan_data:
            task_run.agent_plan = plan_data

    loop_exec.completed_at = datetime.now(UTC)
    loop_exec.status = "completed"
    loop_exec.result = result_data
    await session.commit()

    # 7. Process follow-up tasks and threshold rules
    await process_followup_tasks(task_run, session, services, autonomy_config=autonomy_config)

    await broadcaster.log(task_run.id, "Agent loop complete", phase="agent_loop")
    return result_data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _load_autonomy_config(task_run: TaskRun, session: AsyncSession) -> dict:
    """Load autonomy_config from project_configs."""
    try:
        from sqlalchemy import select as sa_select

        from backend.models import ProjectConfig

        result = await session.execute(
            sa_select(ProjectConfig.autonomy_config).where(
                ProjectConfig.project_id == task_run.project_id
            )
        )
        config = result.scalar_one_or_none()
        return config if isinstance(config, dict) else {}
    except Exception:
        logger.debug("Could not load autonomy_config for run #%s", task_run.id, exc_info=True)
        return {}


async def _wait_for_plan(
    task_run: TaskRun,
    session: AsyncSession,
    ssh,
    workspace: str,
    plan_approval: str,
) -> str | None:
    """Poll for .autodev/plan.json. Return 'awaiting_plan_approval' if require_approval."""
    await broadcaster.log(
        task_run.id,
        f"Waiting for agent plan (plan_approval={plan_approval})",
        phase="agent_loop",
    )
    deadline = time.monotonic() + _PLAN_POLL_TIMEOUT
    while time.monotonic() < deadline:
        plan = await read_workspace_json(ssh, workspace, ".autodev/plan.json")
        if plan:
            await broadcaster.log(task_run.id, "Agent plan ready", phase="agent_loop")
            await broadcaster.event(
                task_run.id,
                "agent_plan_ready",
                {"plan": plan, "plan_approval": plan_approval},
            )
            if plan_approval == "require_approval":
                task_run.agent_plan = plan
                task_run.status = "awaiting_plan_approval"
                await session.commit()
                return "awaiting_plan_approval"
            # show_and_continue: display plan, proceed after short delay
            await asyncio.sleep(5)
            return None
        await asyncio.sleep(_POLL_INTERVAL)

    await broadcaster.log(
        task_run.id,
        "Timed out waiting for agent plan — proceeding anyway",
        level="warning",
        phase="agent_loop",
    )
    return None


async def _poll_until_done(
    *,
    task_run: TaskRun,
    session: AsyncSession,
    ssh,
    workspace: str,
    loop_exec: AgentLoopExecution,
    timeout: int,
) -> dict | None:
    """Poll .autodev/progress.json and .autodev/claude_exit_code until agent finishes."""
    deadline = time.monotonic() + timeout
    last_status = ""
    snapshots: list[dict] = []

    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)

        exit_code_data = await _check_agent_exit(ssh, workspace)
        last_status, snapshots = await _sync_progress(
            ssh, workspace, task_run, session, loop_exec, last_status, snapshots
        )

        if exit_code_data is not None:
            return await _read_agent_result(ssh, workspace, task_run, exit_code_data)

    await broadcaster.log(
        task_run.id,
        f"Agent loop timed out after {timeout}s",
        level="error",
        phase="agent_loop",
    )
    return {"summary": "Agent timed out", "timed_out": True}


async def _check_agent_exit(ssh, workspace: str) -> str | None:
    """Return exit code string if agent has finished, else None."""
    data, _, rc = await ssh.run_command(
        f"cat {shlex.quote(workspace)}/.autodev/claude_exit_code 2>/dev/null"
    )
    return data.strip() if rc == 0 and data.strip().isdigit() else None


async def _sync_progress(
    ssh,
    workspace: str,
    task_run: TaskRun,
    session: AsyncSession,
    loop_exec: AgentLoopExecution,
    last_status: str,
    snapshots: list[dict],
) -> tuple[str, list[dict]]:
    """Stream progress updates from .autodev/progress.json to the broadcaster."""
    progress = await read_workspace_json(ssh, workspace, ".autodev/progress.json")
    if not (progress and isinstance(progress, dict)):
        return last_status, snapshots

    status_msg = progress.get("message", "")
    if status_msg == last_status:
        return last_status, snapshots

    await broadcaster.log(task_run.id, f"[agent] {status_msg}", phase="agent_loop")
    snapshots.append({"timestamp": datetime.now(UTC).isoformat(), **progress})
    loop_exec.progress_snapshots = snapshots[-50:]
    await session.commit()
    return status_msg, snapshots


async def _read_agent_result(ssh, workspace: str, task_run: TaskRun, exit_code_str: str) -> dict:
    """Read result.json after agent exits; log non-zero exit codes."""
    exit_code = int(exit_code_str)
    if exit_code != 0:
        stderr, _, _ = await ssh.run_command(
            f"tail -20 {shlex.quote(workspace)}/.autodev/claude_stderr.log 2>/dev/null"
        )
        await broadcaster.log(
            task_run.id,
            f"Agent exited with code {exit_code}. stderr: {stderr[:500]}",
            level="warning",
            phase="agent_loop",
        )

    raw = await read_workspace_json(ssh, workspace, ".autodev/result.json")
    result: dict | None = raw if isinstance(raw, dict) else None
    if not result:
        result = await _parse_last_output(ssh, workspace)

    return result or {"summary": "Agent completed (no result.json written)", "exit_code": exit_code}


async def _parse_last_output(ssh, workspace: str) -> dict | None:
    """Try to extract a summary from the last line of claude_output.jsonl."""
    stdout, _, rc = await ssh.run_command(
        f"tail -1 {shlex.quote(workspace)}/.autodev/claude_output.jsonl 2>/dev/null"
    )
    if rc != 0 or not stdout.strip():
        return None
    try:
        data = json.loads(stdout.strip())
        # Claude stream-json final message has type="result" or similar
        if isinstance(data, dict):
            return {"summary": data.get("result", data.get("content", "")), "raw": data}
    except json.JSONDecodeError:
        pass
    return None

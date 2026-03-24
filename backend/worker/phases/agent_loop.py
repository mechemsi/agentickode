# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Autonomous agent loop phase.

Replaces the planning → coding → testing → reviewing sequence with a single
phase where Claude Code drives itself end-to-end with full tool access.

Supports two execution modes:
  - **Legacy (default)**: Single fire-and-forget invocation with polling.
  - **Episodic**: Bounded episodes with git checkpoints, stall detection,
    and automatic session recovery. Activated via ``episode_config`` in the
    project's ``autonomy_config``.
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
from backend.models.episodes import Episode
from backend.services.container import ServiceContainer
from backend.services.episode_runner import EpisodeRunner
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._context_builder import (
    build_context_package,
    read_workspace_json,
)
from backend.worker.phases._followup_handler import process_followup_tasks
from backend.worker.phases._helpers import get_ssh_for_run, get_workspace_server

logger = logging.getLogger("agentickode.phases.agent_loop")

PHASE_META = {
    "name": "agent_loop",
    "description": "Autonomous agent loop — Claude Code drives exploration, planning, and execution",
    "default_role": None,
    "default_agent_mode": "task",
}

_POLL_INTERVAL = 5
_DEFAULT_TIMEOUT = 5400
_PLAN_POLL_TIMEOUT = 300


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> dict | None:
    """Execute the autonomous agent loop."""
    await broadcaster.log(task_run.id, "Starting autonomous agent loop", phase="agent_loop")

    autonomy_config = await _load_autonomy_config(task_run, session)
    plan_approval = autonomy_config.get("plan_approval", "none")
    timeout = int(autonomy_config.get("agent_timeout_seconds", _DEFAULT_TIMEOUT))
    ep_config = autonomy_config.get("episode_config")

    # Build context package in workspace
    await broadcaster.log(task_run.id, "Building context package for agent", phase="agent_loop")
    session_id = await build_context_package(
        task_run, session, services, autonomy_config=autonomy_config
    )

    # Create AgentLoopExecution tracking record
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
    server = await get_workspace_server(task_run, session)
    worker_user = server.worker_user or "coder"

    # Handle plan approval gate (same for both modes)
    if plan_approval in ("require_approval", "show_and_continue"):
        result = await _wait_for_plan(task_run, session, ssh, workspace, plan_approval)
        if result == "awaiting_plan_approval":
            loop_exec.status = "waiting_plan"
            await session.commit()
            return result  # type: ignore[return-value]

    # Choose execution mode
    if ep_config and isinstance(ep_config, dict):
        result_data = await _run_episodic(
            task_run,
            session,
            ssh,
            workspace,
            worker_user,
            loop_exec,
            session_id,
            ep_config,
            timeout,
        )
    else:
        result_data = await _run_legacy(
            task_run,
            session,
            ssh,
            workspace,
            worker_user,
            loop_exec,
            timeout,
        )

    # Store results on task_run
    if result_data:
        task_run.coding_results = result_data
        plan_data = await read_workspace_json(ssh, workspace, ".autodev/plan.json")
        if plan_data:
            task_run.agent_plan = plan_data

    loop_exec.completed_at = datetime.now(UTC)
    loop_exec.status = "completed"
    loop_exec.result = result_data
    await session.commit()

    await process_followup_tasks(task_run, session, services, autonomy_config=autonomy_config)
    await broadcaster.log(task_run.id, "Agent loop complete", phase="agent_loop")
    return result_data


# ---------------------------------------------------------------------------
# Episodic execution mode
# ---------------------------------------------------------------------------


async def _run_episodic(
    task_run: TaskRun,
    session: AsyncSession,
    ssh,
    workspace: str,
    worker_user: str,
    loop_exec: AgentLoopExecution,
    session_id: str,
    ep_config: dict,
    timeout: int,
) -> dict | None:
    """Run bounded episodes with git checkpoints and stall recovery."""
    max_episodes = int(ep_config.get("max_episodes", 5))
    max_turns = int(ep_config.get("max_turns_per_episode", 30))
    stall_timeout = int(ep_config.get("stall_timeout_seconds", 600))

    async def log_fn(msg: str, **_kw) -> None:
        await broadcaster.log(task_run.id, msg, phase="agent_loop")

    runner = EpisodeRunner(ssh, workspace, worker_user, log_fn)
    context_summary: str | None = None

    for ep_num in range(1, max_episodes + 1):
        await broadcaster.log(
            task_run.id,
            f"Starting episode {ep_num}/{max_episodes}",
            phase="agent_loop",
        )

        episode = Episode(
            agent_loop_execution_id=loop_exec.id,
            episode_number=ep_num,
            session_id=session_id,
            status="running",
            started_at=datetime.now(UTC),
        )
        session.add(episode)
        await session.commit()

        ep_result = await runner.run_episode(
            ep_num,
            session_id,
            max_turns,
            context_summary=context_summary,
            is_new_session=(ep_num == 1),
            stall_timeout=stall_timeout,
        )

        # Update episode record
        episode.status = (
            "completed"
            if ep_result.completed
            else "stalled"
            if ep_result.stalled
            else "failed"
            if ep_result.errors
            else "completed"
        )
        episode.completed_at = datetime.now(UTC)
        episode.turn_count = ep_result.turn_count
        episode.tokens_used = ep_result.tokens_used
        episode.context_usage_pct = ep_result.context_usage_pct
        episode.git_checkpoint_sha = ep_result.checkpoint_sha
        episode.exit_code = ep_result.exit_code

        # Update loop execution totals
        loop_exec.total_episodes = ep_num
        loop_exec.total_turns += ep_result.turn_count
        loop_exec.total_tokens += ep_result.tokens_used
        loop_exec.last_checkpoint_sha = ep_result.checkpoint_sha
        await session.commit()

        if ep_result.completed:
            return await _read_final_result(ssh, workspace, ep_result)

        if ep_result.stalled:
            await runner.kill_agent()
            context_summary = await _compact_episode(ssh, workspace, ep_num)
            episode.summary = context_summary
            await session.commit()
            continue

        if ep_result.context_exhausted or ep_result.max_turns_reached:
            context_summary = await _compact_episode(ssh, workspace, ep_num)
            episode.summary = context_summary
            await session.commit()
            continue

    await broadcaster.log(
        task_run.id,
        f"All {max_episodes} episodes completed without finishing task",
        level="warning",
        phase="agent_loop",
    )
    return {"summary": "Max episodes reached", "total_episodes": max_episodes}


async def _compact_episode(ssh, workspace: str, episode_num: int) -> str:
    """Build a compact summary of what was accomplished in an episode."""
    ws = shlex.quote(workspace)

    # Get git diff summary
    diff_out, _, _ = await ssh.run_command(
        f"cd {ws} && git log --oneline -5 2>/dev/null || echo '(no commits)'",
        timeout=15,
    )

    # Get list of files changed
    files_out, _, _ = await ssh.run_command(
        f"cd {ws} && git diff --name-only HEAD~1 2>/dev/null || echo '(unknown)'",
        timeout=15,
    )

    return (
        f"Episode {episode_num} completed.\n"
        f"Recent commits:\n{diff_out.strip()}\n\n"
        f"Files changed:\n{files_out.strip()}"
    )


async def _read_final_result(ssh, workspace: str, ep_result) -> dict:
    """Read the final result after successful completion."""
    raw = await read_workspace_json(ssh, workspace, ".autodev/result.json")
    if isinstance(raw, dict):
        return raw
    if ep_result.result_text:
        return {"summary": ep_result.result_text}
    return {"summary": "Agent completed successfully"}


# ---------------------------------------------------------------------------
# Legacy execution mode (original single-invocation)
# ---------------------------------------------------------------------------


async def _run_legacy(
    task_run: TaskRun,
    session: AsyncSession,
    ssh,
    workspace: str,
    worker_user: str,
    loop_exec: AgentLoopExecution,
    timeout: int,
) -> dict | None:
    """Original single fire-and-forget execution (backward compatible)."""
    agent_cmd = (
        f"cd {shlex.quote(workspace)} && "
        f"claude --print --verbose --output-format stream-json "
        f"< .autodev/agent_prompt.md "
        f"> .autodev/claude_output.jsonl 2>.autodev/claude_stderr.log; "
        f"echo $? > .autodev/claude_exit_code"
    )

    if ssh.username == "root":
        await ssh.run_command(
            f"chown -R {worker_user}:{worker_user} {shlex.quote(workspace)}",
            timeout=60,
        )
        user_path = (
            f"/home/{worker_user}/.local/bin"
            f":/home/{worker_user}/.claude/bin"
            ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        )
        inner = f"export PATH={shlex.quote(user_path)} && {agent_cmd}"
        claude_cmd = f"runuser -u {worker_user} -- bash -c {shlex.quote(inner)}"
    else:
        claude_cmd = agent_cmd

    await broadcaster.log(task_run.id, "Launching Claude Code autonomous agent", phase="agent_loop")
    await ssh.fire_and_forget(claude_cmd)

    return await _poll_until_done(
        task_run=task_run,
        session=session,
        ssh=ssh,
        workspace=workspace,
        loop_exec=loop_exec,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Shared helpers
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
        if isinstance(data, dict):
            return {"summary": data.get("result", data.get("content", "")), "raw": data}
    except json.JSONDecodeError:
        pass
    return None

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Coding phase: consolidated mode — single all-in-one invocation."""

import logging
import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentInvocation, PhaseExecution, TaskRun
from backend.services.git import RemoteGitOps
from backend.services.html_to_text import html_to_text
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._coding_utils import (
    CONSOLIDATED_TEMPLATE,
    auto_commit_changes,
    make_results,
)
from backend.worker.phases._helpers import get_ssh_for_run, get_token_usage

logger = logging.getLogger("agentickode.phases.coding")


async def run_consolidated(
    task_run: TaskRun,
    session: AsyncSession,
    adapter: object,
    agent_mode: str,
    system_prompt: str,
    settings_kwargs: dict,
    extra_params: dict,
    use_sessions: bool,
    session_id: str | None,
    session_is_new: bool,
    phase_exec_row: PhaseExecution | None,
    ws_id: int | None,
) -> None:
    """Run a single all-in-one invocation: plan + implement + test + self-review.

    Designed for autonomous agents (like Claude Code) that handle the full
    lifecycle internally. Eliminates the need for separate planning/reviewing
    phases, reducing total invocations from 5-10+ down to 1.
    """
    description = html_to_text(task_run.description) or task_run.title or ""

    # Include init-phase context if available
    plan = task_run.planning_result or {}
    context_docs = plan.get("context_docs", [])
    if context_docs:
        capped: list[str] = []
        total = 0
        for doc in context_docs:
            if total + len(doc) > 4000 and capped:
                break
            capped.append(doc)
            total += len(doc)
        context_section = "## Project Context\n" + "\n\n".join(capped)
    else:
        context_section = ""

    consolidated_prompt = CONSOLIDATED_TEMPLATE.format(
        title=task_run.title or "Task",
        description=description,
        context_section=context_section,
    )

    await broadcaster.log(
        task_run.id,
        "Consolidated mode: single invocation for plan + code + review",
        phase="coding",
    )
    await broadcaster.log(
        task_run.id,
        f"  Prompt ({len(consolidated_prompt)} chars)",
        level="debug",
        phase="coding",
        metadata=make_log_metadata("prompt", prompt_text=consolidated_prompt),
    )

    invocation = AgentInvocation(
        run_id=task_run.id,
        phase_execution_id=phase_exec_row.id if phase_exec_row else None,
        workspace_server_id=ws_id,
        agent_name=adapter.provider_name,
        phase_name="coding",
        subtask_index=0,
        subtask_title=f"Consolidated: {task_run.title}",
        prompt_text=consolidated_prompt,
        system_prompt_text=system_prompt,
        prompt_chars=len(consolidated_prompt) + len(system_prompt),
        session_id=session_id if use_sessions else None,
        status="running",
        started_at=datetime.now(UTC),
    )
    session.add(invocation)
    await session.flush()

    async def _log_ssh(msg: str) -> None:
        await broadcaster.log(task_run.id, f"  {msg}", level="debug", phase="coding")

    is_new_session = use_sessions and session_is_new and session_id is not None

    t0 = time.monotonic()

    if agent_mode == "generate":
        generate_kwargs: dict[str, object] = {
            "system_prompt": system_prompt,
            "temperature": 0.3,
            "num_predict": 8192,
            "log_fn": _log_ssh,
            **settings_kwargs,
            **extra_params,
        }
        if use_sessions and session_id:
            generate_kwargs["session_id"] = session_id
            generate_kwargs["new_session"] = is_new_session
            generate_kwargs["workspace"] = task_run.workspace_path
        agent_output = await adapter.generate(consolidated_prompt, **generate_kwargs)
        exit_code = 0
        agent_stderr = ""
    else:
        task_kwargs: dict[str, object] = {
            "system_prompt": system_prompt,
            "log_fn": _log_ssh,
            **settings_kwargs,
            **extra_params,
        }
        if use_sessions and session_id:
            task_kwargs["session_id"] = session_id
            task_kwargs["new_session"] = is_new_session
        result = await adapter.run_task(
            workspace=task_run.workspace_path,
            instruction=consolidated_prompt,
            **task_kwargs,
        )
        agent_output = result.get("output", "")
        exit_code = result.get("exit_code", 0)
        agent_stderr = result.get("stderr", "")

    elapsed = time.monotonic() - t0

    # Detect file changes via git
    files_changed: list[str] = []
    if task_run.workspace_path:
        try:
            ssh = await get_ssh_for_run(task_run, session)
            remote_git = RemoteGitOps(ssh)
            diff_out = await remote_git.run_git(
                ["diff", "--name-only", "HEAD~1..HEAD"],
                cwd=task_run.workspace_path,
            )
            files_changed = [f for f in diff_out.stdout.strip().split("\n") if f.strip()]
        except Exception:
            logger.debug("Could not detect file changes for consolidated run", exc_info=True)

    # Update invocation record
    invocation.response_text = agent_output
    invocation.response_chars = len(agent_output)
    invocation.duration_seconds = round(elapsed, 1)
    invocation.completed_at = datetime.now(UTC)
    invocation.status = "success" if exit_code == 0 else "failed"
    if exit_code != 0:
        invocation.error_message = agent_stderr[:1000] if agent_stderr else None
    tokens_in, tokens_out, cost, token_source = get_token_usage(
        adapter, adapter.provider_name, invocation.prompt_chars, len(agent_output)
    )
    invocation.estimated_tokens_in = tokens_in
    invocation.estimated_tokens_out = tokens_out
    invocation.estimated_cost_usd = cost
    inv_meta: dict = {"token_source": token_source, "consolidated": True}
    if session_id:
        inv_meta["session_id"] = session_id
    invocation.metadata_ = inv_meta
    await session.flush()

    await broadcaster.log(
        task_run.id,
        f"  Agent response ({len(agent_output)} chars)",
        level="debug",
        phase="coding",
        metadata=make_log_metadata("response", response_text=agent_output, exit_code=exit_code),
    )

    if agent_mode == "task" and exit_code == 127:
        raise RuntimeError(f"Agent not available on server: {agent_stderr}")

    # Auto-commit any remaining uncommitted changes
    auto_committed = await auto_commit_changes(
        task_run, session, f"consolidated: {task_run.title}", _log_ssh
    )
    if auto_committed:
        await broadcaster.log(task_run.id, "  Auto-committed uncommitted changes", phase="coding")

    coding_results = [
        {
            "subtask_title": f"Consolidated: {task_run.title}",
            "files_changed": files_changed,
            "exit_code": exit_code,
            "consolidated": True,
        }
    ]

    task_run.coding_results = make_results(coding_results, session_id)

    # Populate planning_result so the UI can display what was done
    task_run.planning_result = {
        "subtasks": [
            {
                "id": 1,
                "title": task_run.title or "Task",
                "description": description,
                "files_likely_affected": files_changed,
            }
        ],
        "estimated_complexity": "consolidated",
        "consolidated": True,
    }

    # Populate review_result so the UI shows self-review status
    task_run.review_result = {
        "approved": exit_code == 0,
        "issues": [],
        "suggestions": [],
        "strictness": "self-review",
        "consolidated": True,
    }

    await session.commit()

    if exit_code != 0:
        raise RuntimeError(f"Consolidated coding failed (exit={exit_code})")

    elapsed_str = f"{elapsed:.0f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"
    await broadcaster.log(
        task_run.id,
        f"Coding complete (consolidated): 1 invocation in {elapsed_str}",
        phase="coding",
    )

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Coding phase: batch mode — all subtasks in a single agent prompt."""

import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentInvocation, PhaseExecution, TaskRun
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._coding_utils import (
    auto_commit_changes,
    build_batch_prompt,
    make_results,
)
from backend.worker.phases._helpers import get_token_usage


async def run_batch(
    task_run: TaskRun,
    session: AsyncSession,
    subtasks: list[dict],
    adapter: object,
    agent_mode: str,
    system_prompt: str,
    user_template: str,
    settings_kwargs: dict,
    extra_params: dict,
    use_sessions: bool,
    session_id: str | None,
    session_is_new: bool,
    phase_exec_row: PhaseExecution | None,
    ws_id: int | None,
) -> None:
    """Run all subtasks in a single agent prompt (batch mode).

    Saves tokens by sending one combined prompt instead of N separate ones.
    """
    batch_prompt = build_batch_prompt(subtasks, task_run.title or "Task")

    await broadcaster.log(
        task_run.id,
        f"Batch mode: sending {len(subtasks)} subtask(s) in one prompt",
        phase="coding",
    )
    await broadcaster.log(
        task_run.id,
        f"  Prompt ({len(batch_prompt)} chars)",
        level="debug",
        phase="coding",
        metadata=make_log_metadata("prompt", prompt_text=batch_prompt),
    )

    invocation = AgentInvocation(
        run_id=task_run.id,
        phase_execution_id=phase_exec_row.id if phase_exec_row else None,
        workspace_server_id=ws_id,
        agent_name=adapter.provider_name,
        phase_name="coding",
        subtask_index=0,
        subtask_title=f"Batch: {len(subtasks)} subtasks",
        prompt_text=batch_prompt,
        system_prompt_text=system_prompt,
        prompt_chars=len(batch_prompt) + len(system_prompt),
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
            if is_new_session:
                generate_kwargs["new_session"] = True
            generate_kwargs["workspace"] = task_run.workspace_path
        agent_output = await adapter.generate(batch_prompt, **generate_kwargs)
        elapsed = time.monotonic() - t0
        files_changed: list[str] = []
        exit_code: int | str = 0
        agent_stderr = ""
    else:
        result = await adapter.run_task(
            workspace=task_run.workspace_path,
            instruction=batch_prompt,
            system_prompt=system_prompt,
            max_iterations=50,
            log_fn=_log_ssh,
            session_id=session_id if use_sessions else None,
            new_session=is_new_session,
            **settings_kwargs,
            **extra_params,
        )
        elapsed = time.monotonic() - t0
        files_changed = result.get("files_changed", [])
        exit_code = result.get("exit_code", "?")
        agent_stderr = result.get("stderr", "")
        agent_output = result.get("output", "")

    # Update invocation
    invocation_metadata: dict = {}
    if agent_mode == "task":
        invocation_metadata["command"] = result.get("command", "")
    if session_id:
        invocation_metadata["session_id"] = session_id
    invocation_metadata["batch_mode"] = True
    invocation_metadata["subtask_count"] = len(subtasks)

    invocation.response_text = agent_output
    invocation.response_chars = len(agent_output)
    invocation.exit_code = exit_code if isinstance(exit_code, int) else None
    invocation.files_changed = files_changed
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
    invocation_metadata["token_source"] = token_source
    invocation.metadata_ = invocation_metadata or None
    await session.flush()

    await broadcaster.log(
        task_run.id,
        f"  Agent response ({len(agent_output)} chars)",
        level="debug",
        phase="coding",
        metadata=make_log_metadata(
            "response",
            response_text=agent_output,
            exit_code=exit_code,
        ),
    )

    if agent_mode == "task" and exit_code == 127:
        raise RuntimeError(f"Agent not available on server: {agent_stderr}")

    # Auto-commit any remaining uncommitted changes
    auto_committed = await auto_commit_changes(
        task_run,
        session,
        f"batch: {len(subtasks)} subtasks",
        _log_ssh,
    )
    if auto_committed:
        await broadcaster.log(
            task_run.id,
            "  Auto-committed uncommitted changes",
            phase="coding",
        )

    # Build results — one entry per subtask, all sharing the same files_changed
    coding_results = [
        {
            "subtask_title": st.get("title", f"Subtask {j + 1}"),
            "files_changed": files_changed if j == 0 else [],
            "exit_code": exit_code,
            "batch_mode": True,
        }
        for j, st in enumerate(subtasks)
    ]

    task_run.coding_results = make_results(coding_results, session_id)
    await session.commit()

    if exit_code != 0:
        raise RuntimeError(f"Batch coding failed (exit={exit_code})")

    if agent_mode == "task" and not files_changed:
        raise RuntimeError(
            f"Batch coding produced no file changes across {len(subtasks)} subtask(s)"
        )

    elapsed_str = f"{elapsed:.0f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"
    await broadcaster.log(
        task_run.id,
        f"Coding complete (batch): {len(subtasks)} subtask(s) in {elapsed_str}",
        phase="coding",
    )

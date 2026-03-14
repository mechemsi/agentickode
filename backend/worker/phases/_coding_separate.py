# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Separate subtask execution — run each subtask as an individual agent invocation."""

import logging
import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentInvocation, PhaseExecution, TaskRun
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._coding_utils import (
    auto_commit_changes,
    build_coding_prompt,
    build_continuation_prompt,
    make_results,
)
from backend.worker.phases._helpers import get_token_usage

logger = logging.getLogger("agentickode.phases.coding")


async def run_separate(
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
    """Run each subtask as an individual agent invocation (separate mode).

    Supports session continuity — later subtasks use shorter continuation prompts.
    """
    coding_results = []
    previous_changes: list[str] = []
    failed_count = 0

    for i, subtask in enumerate(subtasks):
        title = subtask.get("title", f"Subtask {i + 1}")
        files_hint = subtask.get("files_likely_affected", [])
        await broadcaster.log(
            task_run.id,
            f"Subtask {i + 1}/{len(subtasks)}: {title}",
            phase="coding",
        )
        if files_hint:
            await broadcaster.log(
                task_run.id,
                f"  Files: {', '.join(files_hint[:5])}",
                level="debug",
                phase="coding",
            )

        # For subtasks after the first in a session, use a shorter continuation prompt
        # (the agent already has project context from the conversation history)
        is_continuation = use_sessions and i > 0 and session_id is not None
        if is_continuation:
            coding_prompt = build_continuation_prompt(subtask)
        else:
            coding_prompt = build_coding_prompt(subtask, previous_changes, user_template)

        # Log the full prompt with metadata
        await broadcaster.log(
            task_run.id,
            f"  Prompt ({len(coding_prompt)} chars)",
            level="debug",
            phase="coding",
            metadata=make_log_metadata("prompt", prompt_text=coding_prompt),
        )

        await broadcaster.log(
            task_run.id,
            f"  Running agent ({adapter.provider_name}) — this may take a few minutes",
            phase="coding",
        )

        # Record invocation start
        # Skip system_prompt_text on continuation — agent already has it in session history
        invocation = AgentInvocation(
            run_id=task_run.id,
            phase_execution_id=phase_exec_row.id if phase_exec_row else None,
            workspace_server_id=ws_id,
            agent_name=adapter.provider_name,
            phase_name="coding",
            subtask_index=i,
            subtask_title=title,
            prompt_text=coding_prompt,
            system_prompt_text=system_prompt if not is_continuation else None,
            prompt_chars=len(coding_prompt) + (len(system_prompt) if not is_continuation else 0),
            session_id=session_id if use_sessions else None,
            status="running",
            started_at=datetime.now(UTC),
        )
        session.add(invocation)
        await session.flush()

        # Log callback that broadcasts SSH commands to the UI in real-time
        async def _log_ssh(msg: str) -> None:
            await broadcaster.log(task_run.id, f"  {msg}", level="debug", phase="coding")

        # new_session=True only when WE create the session (i==0 and not inherited).
        # Inherited sessions from planning must be RESUMED, not re-created.
        is_new_session = use_sessions and i == 0 and session_is_new and session_id is not None

        t0 = time.monotonic()

        if agent_mode == "generate":
            # Generate mode: prompt-based (like planning/reviewing)
            generate_kwargs: dict[str, object] = {
                "system_prompt": system_prompt if not is_continuation else None,
                "temperature": 0.3,
                "num_predict": 4096,
                "log_fn": _log_ssh,
                **settings_kwargs,
                **extra_params,
            }
            if use_sessions and session_id:
                generate_kwargs["session_id"] = session_id
                if is_new_session:
                    generate_kwargs["new_session"] = True
                generate_kwargs["workspace"] = task_run.workspace_path
            agent_output = await adapter.generate(coding_prompt, **generate_kwargs)
            elapsed = time.monotonic() - t0
            files_changed: list[str] = []
            exit_code: int | str = 0
            agent_stderr = ""
        else:
            # Task mode: workspace execution (default for coding)
            result = await adapter.run_task(
                workspace=task_run.workspace_path,
                instruction=coding_prompt,
                # Skip system_prompt on session continuation — agent already has context
                system_prompt=system_prompt if not is_continuation else None,
                max_iterations=20,
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

        # Build invocation metadata with session_id for traceability
        invocation_metadata: dict = {}
        if agent_mode == "task":
            invocation_metadata["command"] = result.get("command", "")
        if session_id:
            invocation_metadata["session_id"] = session_id

        # Update invocation with results
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

        # Log agent response with metadata
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

        # Detect agent not found (task mode only)
        if agent_mode == "task" and exit_code == 127:
            await broadcaster.log(
                task_run.id,
                f"  Agent not available: {agent_stderr or 'not found'}",
                level="error",
                phase="coding",
            )
            raise RuntimeError(f"Agent not available on server: {agent_stderr}")

        # Track failures
        if exit_code != 0:
            failed_count += 1
            await broadcaster.log(
                task_run.id,
                f"  Subtask FAILED (exit={exit_code})",
                level="error",
                phase="coding",
            )

        # Auto-commit any uncommitted changes left by the agent
        auto_committed = await auto_commit_changes(task_run, session, title, _log_ssh)
        if auto_committed:
            await broadcaster.log(
                task_run.id,
                f"  Auto-committed uncommitted changes for: {title}",
                phase="coding",
            )

        coding_results.append(
            {
                "subtask_title": title,
                "files_changed": files_changed,
                "exit_code": exit_code,
            }
        )
        previous_changes.extend(files_changed)

        # Persist results after each subtask so progress is visible immediately
        task_run.coding_results = make_results(coding_results, session_id)
        await session.commit()

        elapsed_str = f"{elapsed:.0f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"
        files_str = ", ".join(files_changed[:5]) if files_changed else "none detected"
        await broadcaster.log(
            task_run.id,
            f"  Done in {elapsed_str} (exit={exit_code}, files: {files_str})",
            phase="coding",
        )

    # Fail early if ALL subtasks failed
    if failed_count == len(subtasks):
        raise RuntimeError(
            f"All {len(subtasks)} subtask(s) failed — agent returned non-zero exit codes"
        )

    # Fail if no files were changed at all (only in task mode where files are tracked)
    if agent_mode == "task" and not previous_changes:
        raise RuntimeError(f"Coding produced no file changes across {len(subtasks)} subtask(s)")

    await broadcaster.log(
        task_run.id,
        f"Coding complete: {len(coding_results)} subtask(s) ({failed_count} failed)",
        phase="coding",
    )

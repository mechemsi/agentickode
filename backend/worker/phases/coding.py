# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 3: Coding — execute subtasks via role adapter + run tests.

Ported from activities.py run_coder_agent + run_tests.
Test execution runs on the remote workspace server via SSH.
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentInvocation, PhaseExecution, TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps
from backend.services.html_to_text import html_to_text
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._helpers import (
    apply_phase_command_overrides,
    ensure_agent_ready,
    get_agent_mode,
    get_agent_settings_kwargs,
    get_phase_role,
    get_ssh_for_run,
    get_token_usage,
    get_workspace_server_id,
    phase_uses_agent,
)
from backend.worker.phases._prompt_resolver import resolve_prompts

logger = logging.getLogger("agentickode.phases.coding")

PHASE_META = {
    "description": "Execute subtasks via AI coding agent",
    "default_role": "coder",
    "default_agent_mode": "task",
}

FALLBACK_SYSTEM_PROMPT = (
    "You are an expert software developer implementing code changes.\n\n"
    "IMPORTANT: You are running autonomously. Do NOT ask clarifying questions. "
    "Make your best judgment and implement the changes directly.\n\n"
    "Follow existing code patterns and style. Add appropriate error handling. "
    "Write or update tests if applicable. Commit changes with descriptive messages."
)

FALLBACK_USER_TEMPLATE = """## Subtask
{title}

## Description
{description}

## Files Likely Affected
{files}

## Previous Changes in This Session
{prev}

## Instructions
1. Implement the subtask as described — do NOT ask questions, just implement
2. Follow existing code patterns and style
3. Add appropriate error handling
4. Write or update tests if applicable
5. Commit changes with a descriptive message
6. If the task is ambiguous, use your best judgment and proceed"""

CONTINUATION_TEMPLATE = """## Next Subtask
{title}

## Description
{description}

## Files Likely Affected
{files}

Continue from where you left off. The previous changes are already in the workspace."""

BATCH_TEMPLATE = """## Task: {task_title}

You have {count} subtasks to implement. Complete ALL of them in order.
Commit after each subtask with a descriptive message.

{subtask_list}

## Instructions
1. Implement ALL subtasks in order — do NOT ask questions, just implement
2. Follow existing code patterns and style
3. Add appropriate error handling
4. Write or update tests if applicable
5. Commit changes after each subtask with a descriptive message
6. If a subtask is ambiguous, use your best judgment and proceed"""


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> None:
    # Skip if agent is disabled for this phase
    if not phase_uses_agent("coding", phase_config):
        await broadcaster.log(task_run.id, "Agent disabled for coding — skipping", phase="coding")
        task_run.coding_results = {"results": [], "agent_skipped": True}
        await session.commit()
        return

    plan = task_run.planning_result or {}
    subtasks = plan.get("subtasks", [])

    # fix-pr: build subtask from PR comments if available
    coding_data = task_run.coding_results or {}
    pr_comments = coding_data.get("pr_comments", [])
    if not subtasks and pr_comments:
        comment_text = _format_pr_comments(pr_comments)
        subtasks = [
            {
                "title": f"Fix PR feedback: {task_run.title}",
                "description": (
                    f"{html_to_text(task_run.description) or task_run.title}"
                    f"\n\n## PR Review Comments\n{comment_text}"
                ),
                "files_likely_affected": [],
            }
        ]
        await broadcaster.log(
            task_run.id,
            f"Built subtask from {len(pr_comments)} PR comment(s)",
            phase="coding",
        )

    if not subtasks:
        # Synthesize a single subtask from task title+description (hotfix/small-task workflows)
        if task_run.title:
            subtasks = [
                {
                    "title": task_run.title,
                    "description": html_to_text(task_run.description) or task_run.title,
                    "files_likely_affected": [],
                }
            ]
            await broadcaster.log(
                task_run.id,
                "No planning subtasks — synthesizing from task description",
                phase="coding",
            )
        else:
            await broadcaster.log(
                task_run.id, "No subtasks to execute", level="warning", phase="coding"
            )
            task_run.coding_results = {"results": []}
            await session.commit()
            return

    # Resolve phase_execution early for agent_override and linking
    pe_result = await session.execute(
        select(PhaseExecution).where(
            PhaseExecution.run_id == task_run.id,
            PhaseExecution.phase_name == "coding",
        )
    )
    phase_exec_row = pe_result.scalar_one_or_none()

    ws_id = await get_workspace_server_id(task_run, session)

    # Check for A/B comparison mode
    comparison_cfg = (phase_config or {}).get("params", {}).get("comparison")
    if comparison_cfg and isinstance(comparison_cfg, dict):
        from backend.worker.phases._comparison import run_comparison

        await run_comparison(
            task_run,
            session,
            services,
            phase_config,
            subtasks,
            phase_exec_row,
            ws_id,
        )
        return

    role = get_phase_role("coding", phase_config, phase_exec_row)
    resolved = await services.role_resolver.resolve(role, session, ws_id, phase_name="coding")
    adapter = resolved.adapter
    config = resolved.role_config
    settings_kwargs = get_agent_settings_kwargs(resolved.agent_settings, phase_config)
    apply_phase_command_overrides(adapter, phase_config)

    agent_mode = get_agent_mode("coding", phase_config)

    # Ensure agent is installed and non-root user is set up (auto-install if needed)
    async def _phase_log(msg: str, level: str = "info") -> None:
        await broadcaster.log(task_run.id, msg, level=level, phase="coding")

    if agent_mode == "task":
        await ensure_agent_ready(adapter, log_fn=_phase_log, agent_settings=resolved.agent_settings)

    system_prompt, user_template, extra_params, project_env_vars = await resolve_prompts(
        config,
        adapter,
        session,
        FALLBACK_SYSTEM_PROMPT,
        FALLBACK_USER_TEMPLATE,
        project_id=task_run.project_id,
        phase_name="coding",
    )
    if project_env_vars:
        existing_env = settings_kwargs.get("environment_vars", {})
        settings_kwargs["environment_vars"] = {**existing_env, **project_env_vars}

    await broadcaster.log(
        task_run.id,
        f"Using {adapter.provider_name} for {len(subtasks)} subtask(s)",
        phase="coding",
        metadata=make_log_metadata("system_prompt", system_prompt_text=system_prompt),
    )

    # Determine session continuity: generate session_id if agent supports it
    use_sessions = getattr(adapter, "supports_session", False)
    session_id: str | None = None
    session_is_new = False  # True only when WE create the session (not inherited)

    if use_sessions:
        # Check if a previous phase left a session_id we can continue
        prev_session = _get_previous_session_id(task_run)
        if prev_session:
            session_id = prev_session
            await broadcaster.log(
                task_run.id,
                f"Continuing agent session from previous phase: {session_id[:8]}...",
                phase="coding",
            )
        else:
            # Start a fresh session for this coding run
            session_id = str(uuid.uuid4())
            session_is_new = True
            await broadcaster.log(
                task_run.id,
                f"Starting new agent session: {session_id[:8]}...",
                phase="coding",
            )

    # Determine subtask execution mode: "separate" (default) or "batch" (one prompt)
    subtask_mode = (phase_config or {}).get("params", {}).get("subtask_mode", "batch")
    if subtask_mode == "batch" and len(subtasks) > 1:
        await _run_batch(
            task_run,
            session,
            subtasks,
            adapter,
            agent_mode,
            system_prompt,
            user_template,
            settings_kwargs,
            extra_params,
            use_sessions,
            session_id,
            session_is_new,
            phase_exec_row,
            ws_id,
        )
        return

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
            coding_prompt = _build_continuation_prompt(subtask)
        else:
            coding_prompt = _build_coding_prompt(subtask, previous_changes, user_template)

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
        auto_committed = await _auto_commit_changes(task_run, session, title, _log_ssh)
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
        task_run.coding_results = _make_results(coding_results, session_id)
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


async def _run_batch(
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
    batch_prompt = _build_batch_prompt(subtasks, task_run.title or "Task")

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
    auto_committed = await _auto_commit_changes(
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

    task_run.coding_results = _make_results(coding_results, session_id)
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


def _build_batch_prompt(subtasks: list[dict], task_title: str) -> str:
    """Combine all subtasks into a single prompt for batch execution."""
    parts: list[str] = []
    for i, st in enumerate(subtasks):
        title = st.get("title", f"Subtask {i + 1}")
        desc = st.get("description", "")
        files = ", ".join(st.get("files_likely_affected", []))
        part = f"### Subtask {i + 1}: {title}\n{desc}"
        if files:
            part += f"\nFiles: {files}"
        parts.append(part)

    subtask_list = "\n\n".join(parts)
    return BATCH_TEMPLATE.format(
        task_title=task_title,
        count=len(subtasks),
        subtask_list=subtask_list,
    )


async def _auto_commit_changes(
    task_run: TaskRun,
    session: AsyncSession,
    subtask_title: str,
    log_fn: Callable[..., Awaitable[None]],
) -> bool:
    """Check for uncommitted changes and auto-commit them.

    Returns True if a commit was made, False if workspace was clean.
    """
    workspace = task_run.workspace_path
    if not workspace:
        return False

    try:
        ssh = await get_ssh_for_run(task_run, session)
        remote_git = RemoteGitOps(ssh)

        # Mark directory safe (root running git in worker-owned dir)
        await remote_git._mark_safe_directory(workspace)

        # Check for uncommitted changes (staged + unstaged + untracked)
        status = await remote_git.run_git(["status", "--porcelain"], cwd=workspace)
        if not status.stdout or not status.stdout.strip():
            return False

        # Stage all changes and commit
        await remote_git.run_git(["add", "-A"], cwd=workspace)
        msg = f"feat: {subtask_title[:100]}"
        await remote_git.run_git(
            ["commit", "-m", msg, "--allow-empty-message"],
            cwd=workspace,
        )
        return True
    except Exception as e:
        logger.warning("Auto-commit failed for run #%d: %s", task_run.id, e)
        await log_fn(f"Auto-commit skipped: {e}")
        return False


def _build_coding_prompt(subtask: dict, previous_changes: list[str], template: str) -> str:
    # Cap previous_changes to last 10 files to avoid unbounded token growth
    capped = previous_changes[-10:] if len(previous_changes) > 10 else previous_changes
    prev = "\n".join(capped) if capped else "None yet"
    if len(previous_changes) > 10:
        prev = f"[...{len(previous_changes) - 10} earlier files omitted]\n{prev}"
    files = ", ".join(subtask.get("files_likely_affected", []))
    return template.format(
        title=subtask.get("title", ""),
        description=subtask.get("description", ""),
        files=files,
        prev=prev,
    )


def _build_continuation_prompt(subtask: dict) -> str:
    """Build a shorter prompt for session continuation.

    When an agent session is active, the agent already has full project context
    from the conversation history, so we send a minimal follow-up message.
    """
    title = subtask.get("title", "")
    desc = subtask.get("description", "")
    files = ", ".join(subtask.get("files_likely_affected", []))
    return CONTINUATION_TEMPLATE.format(title=title, description=desc, files=files)


def _get_previous_session_id(task_run: TaskRun) -> str | None:
    """Check if a previous phase stored a session_id we can continue from.

    Currently checks the planning_result — if planning was done via the same
    session-capable agent, it may have stored a session_id.
    """
    planning = task_run.planning_result
    if planning and isinstance(planning, dict):
        sid = planning.get("session_id")
        if sid and isinstance(sid, str):
            return sid
    return None


def _make_results(results: list, session_id: str | None = None) -> dict:
    """Build coding results dict, including session_id for cross-phase continuity."""
    data: dict = {"results": results}
    if session_id:
        data["session_id"] = session_id
    return data


def _format_pr_comments(comments: list[dict]) -> str:
    """Format PR review comments into readable text for the coding agent."""
    lines: list[str] = []
    for c in comments:
        body = c.get("body", "").strip()
        if not body:
            continue
        path = c.get("path", "")
        line = c.get("line") or c.get("original_line")
        loc = f"`{path}:{line}`" if path and line else (f"`{path}`" if path else "")
        prefix = f"- {loc} " if loc else "- "
        lines.append(f"{prefix}{body}")
    return "\n".join(lines) if lines else "No actionable comments found."

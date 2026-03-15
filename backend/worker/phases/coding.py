# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 3: Coding — execute subtasks via role adapter + run tests.

Ported from activities.py run_coder_agent + run_tests.
Test execution runs on the remote workspace server via SSH.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PhaseExecution, TaskRun
from backend.services.container import ServiceContainer
from backend.services.html_to_text import html_to_text
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._coding_batch import run_batch
from backend.worker.phases._coding_consolidated import run_consolidated
from backend.worker.phases._coding_separate import run_separate
from backend.worker.phases._coding_utils import (
    FALLBACK_SYSTEM_PROMPT,
    FALLBACK_USER_TEMPLATE,
    format_pr_comments,
    get_previous_session_id,
)
from backend.worker.phases._helpers import (
    apply_phase_command_overrides,
    ensure_agent_ready,
    get_agent_mode,
    get_agent_settings_kwargs,
    get_phase_role,
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
        comment_text = format_pr_comments(pr_comments)
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
    if resolved.is_fallback and resolved.tried:
        tried_msg = ", ".join(resolved.tried)
        await broadcaster.log(
            task_run.id,
            f"⚠ Configured agents failed: {tried_msg} — fell back to Ollama",
            level="warning",
            phase="coding",
        )
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
        prev_session = get_previous_session_id(task_run)
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

    # Consolidated mode: single invocation handles plan + code + review
    # Priority: run/workflow phase_config > agent default > global fallback (True)
    params = (phase_config or {}).get("params", {})
    if "consolidated" in params:
        consolidated = params["consolidated"]
    elif resolved.agent_settings and resolved.agent_settings.consolidated_default is not None:
        consolidated = resolved.agent_settings.consolidated_default
    else:
        consolidated = True
    if consolidated:
        # Skip reviewing phase — consolidated mode self-reviews
        await _skip_reviewing_phase(task_run, session)

        await run_consolidated(
            task_run,
            session,
            adapter,
            agent_mode,
            system_prompt,
            settings_kwargs,
            extra_params,
            use_sessions,
            session_id,
            session_is_new,
            phase_exec_row,
            ws_id,
        )
        return

    # Determine subtask execution mode: "separate" (default) or "batch" (one prompt)
    subtask_mode = (phase_config or {}).get("params", {}).get("subtask_mode", "batch")
    if subtask_mode == "batch" and len(subtasks) > 1:
        await run_batch(
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

    await run_separate(
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


async def _skip_reviewing_phase(task_run: TaskRun, session: AsyncSession) -> None:
    """Mark the reviewing phase as skipped when consolidated mode is active."""
    from backend.repositories.phase_execution_repo import PhaseExecutionRepository

    pe_repo = PhaseExecutionRepository(session)
    phases = await pe_repo.get_by_run(task_run.id)
    for pe in phases:
        if pe.phase_name == "reviewing" and pe.status == "pending":
            await pe_repo.update_status(pe, "skipped")
            await broadcaster.log(
                task_run.id,
                "Skipped reviewing — consolidated mode self-reviews in coding phase",
                phase="reviewing",
            )
    await session.flush()

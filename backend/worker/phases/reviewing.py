# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 4: Reviewing — AI code review with retry loop.

Ported from activities.py run_reviewer_agent + workflows.py _run_review_with_retry.
Git diff is obtained from the remote workspace server via SSH.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PhaseExecution, TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._helpers import (
    apply_phase_command_overrides,
    ensure_agent_ready,
    get_agent_mode,
    get_agent_settings_kwargs,
    get_phase_role,
    get_ssh_for_run,
    get_workspace_server_id,
    phase_uses_agent,
)
from backend.worker.phases._prompt_resolver import resolve_prompts
from backend.worker.phases._reviewing_loop import run_review_loop

logger = logging.getLogger("agentickode.phases.reviewing")

PHASE_META = {
    "description": "AI code review with auto-fix retry loop",
    "default_role": "reviewer",
    "default_agent_mode": "generate",
}

FALLBACK_SYSTEM_PROMPT = (
    "You are a senior code reviewer. Review changes for correctness, quality, "
    "error handling, security, and performance."
)

FALLBACK_USER_TEMPLATE = """## Task Context
Title: {title}
Description: {description}

## Files Changed
{files_changed}

## Diff
```diff
{diff_text}
```

## Review Criteria
1. Code correctness - does it implement the requirement?
2. Code quality - is it readable, maintainable?
3. Error handling - are edge cases covered?
4. Security - any vulnerabilities introduced?
5. Performance - any obvious inefficiencies?

Respond in JSON format:
{{
  "approved": true,
  "issues": [
    {{"severity": "critical|major|minor", "file": "...", "line": 0, "description": "..."}}
  ],
  "suggestions": ["..."]
}}"""


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> None:
    # Skip if agent is disabled for this phase
    if not phase_uses_agent("reviewing", phase_config):
        await broadcaster.log(
            task_run.id, "Agent disabled for reviewing — skipping", phase="reviewing"
        )
        task_run.review_result = {"approved": True, "issues": [], "agent_skipped": True}
        await session.commit()
        return

    coding_data = task_run.coding_results or {}
    results = coding_data.get("results", [])
    all_files: list[str] = []
    for r in results:
        all_files.extend(r.get("files_changed", []))

    # Resolve phase_execution early for agent_override and linking
    pe_result = await session.execute(
        select(PhaseExecution).where(
            PhaseExecution.run_id == task_run.id,
            PhaseExecution.phase_name == "reviewing",
        )
    )
    phase_exec_row = pe_result.scalar_one_or_none()

    ws_id = await get_workspace_server_id(task_run, session)
    role = get_phase_role("reviewing", phase_config, phase_exec_row)
    resolved = await services.role_resolver.resolve(role, session, ws_id, phase_name="reviewing")
    if resolved.is_fallback and resolved.tried:
        tried_msg = ", ".join(resolved.tried)
        await broadcaster.log(
            task_run.id,
            f"⚠ Configured agents failed: {tried_msg} — fell back to Ollama",
            level="warning",
            phase="reviewing",
        )
    reviewer = resolved.adapter
    config = resolved.role_config
    settings_kwargs = get_agent_settings_kwargs(resolved.agent_settings, phase_config)
    apply_phase_command_overrides(reviewer, phase_config)

    system_prompt, user_template, extra_params, project_env_vars = await resolve_prompts(
        config,
        reviewer,
        session,
        FALLBACK_SYSTEM_PROMPT,
        FALLBACK_USER_TEMPLATE,
        project_id=task_run.project_id,
        phase_name="reviewing",
    )
    if project_env_vars:
        existing_env = settings_kwargs.get("environment_vars", {})
        settings_kwargs["environment_vars"] = {**existing_env, **project_env_vars}
    temperature = config.default_temperature if config else 0.2
    num_predict = config.default_num_predict if config else 2048

    # Read strictness from phase config (default: critical_only for backward compat)
    params = (phase_config or {}).get("params", {})
    strictness = params.get("review_strictness", "critical_only")

    # SSH/git are only needed if we don't have a pre-fetched PR diff
    pr_diff = coding_data.get("pr_diff")
    if pr_diff:
        remote_git = None
    else:
        ssh = await get_ssh_for_run(task_run, session)
        remote_git = RemoteGitOps(ssh)

    await broadcaster.log(
        task_run.id,
        f"Reviewing {len(all_files)} changed file(s) via {reviewer.provider_name}",
        phase="reviewing",
        metadata=make_log_metadata("system_prompt", system_prompt_text=system_prompt),
    )

    # Pick up session_id from coding phase for cross-phase conversation continuity
    use_sessions = getattr(reviewer, "supports_session", False)
    session_id: str | None = None

    if use_sessions:
        raw_sid = coding_data.get("session_id")
        if raw_sid and isinstance(raw_sid, str):
            session_id = raw_sid
            await broadcaster.log(
                task_run.id,
                f"Continuing agent session from coding phase: {session_id[:8]}...",
                phase="reviewing",
            )

    agent_mode = get_agent_mode("reviewing", phase_config)

    # Build review_result structure with iteration tracking
    review_result: dict = {"strictness": strictness}
    if session_id:
        review_result["session_id"] = session_id

    # Ensure agent binary is accessible before entering retry loop
    async def _review_setup_log(msg: str, level: str = "info") -> None:
        await broadcaster.log(task_run.id, msg, level=level, phase="reviewing")

    await ensure_agent_ready(
        reviewer, log_fn=_review_setup_log, agent_settings=resolved.agent_settings
    )

    await run_review_loop(
        task_run,
        session,
        services,
        reviewer=reviewer,
        phase_exec_row=phase_exec_row,
        ws_id=ws_id,
        settings_kwargs=settings_kwargs,
        extra_params=extra_params,
        system_prompt=system_prompt,
        user_template=user_template,
        temperature=temperature,
        num_predict=num_predict,
        strictness=strictness,
        all_files=all_files,
        pr_diff=pr_diff,
        remote_git=remote_git,
        session_id=session_id,
        agent_mode=agent_mode,
        review_result=review_result,
    )

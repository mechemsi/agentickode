# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 4: Reviewing — AI code review with retry loop.

Ported from activities.py run_reviewer_agent + workflows.py _run_review_with_retry.
Git diff is obtained from the remote workspace server via SSH.
"""

import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentInvocation, PhaseExecution, TaskRun
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
    get_token_usage,
    get_workspace_server_id,
    phase_uses_agent,
)
from backend.worker.phases._prompt_resolver import resolve_prompts
from backend.worker.phases._review_helpers import (
    build_fix_instruction,
    build_review_prompt,
    parse_review_response,
    record_iteration,
    should_retry,
)

logger = logging.getLogger("autodev.phases.reviewing")

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
    all_files = []
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

    retry_count = 0
    max_retries = task_run.max_retries
    prev_issues: list[dict] | None = None

    # Build review_result structure with iteration tracking
    review_result: dict = {"strictness": strictness}
    if session_id:
        review_result["session_id"] = session_id

    async def _log_ssh(msg: str) -> None:
        await broadcaster.log(task_run.id, f"  {msg}", level="debug", phase="reviewing")

    # Ensure agent binary is accessible before entering retry loop
    async def _review_setup_log(msg: str, level: str = "info") -> None:
        await broadcaster.log(task_run.id, msg, level=level, phase="reviewing")

    await ensure_agent_ready(
        reviewer, log_fn=_review_setup_log, agent_settings=resolved.agent_settings
    )

    while retry_count <= max_retries:
        attempt = retry_count + 1
        await broadcaster.log(
            task_run.id,
            f"Review attempt {attempt}/{max_retries + 1}",
            phase="reviewing",
        )

        # Get diff — skip re-fetching on retries with active session
        if retry_count > 0 and session_id:
            # Session already has the diff context; use a shorter re-review prompt
            prompt = (
                "Please re-review the code with the fixes applied. "
                "The diff context is already in our conversation. "
                "Respond in the same JSON format as before."
            )
        else:
            diff_text = await _get_diff(task_run, pr_diff, remote_git, _log_ssh)
            prompt = build_review_prompt(
                user_template, task_run.title, task_run.description, all_files, diff_text
            )

        await broadcaster.log(
            task_run.id,
            "Sending review prompt to agent",
            phase="reviewing",
            metadata=make_log_metadata("prompt", prompt_text=prompt),
        )

        review_metadata: dict = {}
        if session_id:
            review_metadata["session_id"] = session_id

        review_invocation = AgentInvocation(
            run_id=task_run.id,
            phase_execution_id=phase_exec_row.id if phase_exec_row else None,
            workspace_server_id=ws_id,
            agent_name=reviewer.provider_name,
            phase_name="reviewing",
            subtask_index=retry_count,
            subtask_title=f"Review attempt {attempt}",
            prompt_text=prompt,
            system_prompt_text=system_prompt if not session_id else None,
            prompt_chars=len(prompt) + (len(system_prompt) if not session_id else 0),
            session_id=session_id,
            status="running",
            started_at=datetime.now(UTC),
            metadata_=review_metadata or None,
        )
        session.add(review_invocation)
        await session.flush()

        t0 = time.monotonic()
        if agent_mode == "task":
            # Task mode: run as workspace execution
            task_result = await reviewer.run_task(
                workspace=task_run.workspace_path,
                instruction=prompt,
                system_prompt=system_prompt if not session_id else None,
                log_fn=_log_ssh,
                session_id=session_id,
                **settings_kwargs,
                **extra_params,
            )
            response_text = task_result.get("output", "")
        else:
            # Generate mode: prompt-based (default for reviewing)
            response_text = await reviewer.generate(
                prompt,
                system_prompt=system_prompt if not session_id else None,
                temperature=temperature,
                num_predict=num_predict,
                log_fn=_log_ssh,
                session_id=session_id,
                workspace=task_run.workspace_path,
                **settings_kwargs,
                **extra_params,
            )
        elapsed = time.monotonic() - t0

        review_invocation.response_text = response_text
        review_invocation.response_chars = len(response_text)
        review_invocation.duration_seconds = round(elapsed, 1)
        review_invocation.completed_at = datetime.now(UTC)
        review_invocation.status = "success"
        tokens_in, tokens_out, cost, token_source = get_token_usage(
            reviewer, reviewer.provider_name, review_invocation.prompt_chars, len(response_text)
        )
        review_invocation.estimated_tokens_in = tokens_in
        review_invocation.estimated_tokens_out = tokens_out
        review_invocation.estimated_cost_usd = cost
        if review_invocation.metadata_ is None:
            review_invocation.metadata_ = {}
        review_invocation.metadata_["token_source"] = token_source  # type: ignore[index]
        await session.flush()

        await broadcaster.log(
            task_run.id,
            f"Received response ({len(response_text)} chars), parsing",
            level="debug",
            phase="reviewing",
            metadata=make_log_metadata("response", response_text=response_text),
        )

        parsed = parse_review_response(response_text)

        # Determine if we will retry (needed to set fix_applied in iteration)
        will_retry = should_retry(parsed, strictness, retry_count, max_retries)
        fix_instr = build_fix_instruction(parsed, strictness) if will_retry else None

        # Record iteration
        review_result = record_iteration(
            review_result, attempt, parsed, will_retry, fix_instr, prev_issues
        )

        # Update top-level review_result fields
        review_result["approved"] = parsed["approved"]
        review_result["issues"] = parsed["issues"]
        review_result["suggestions"] = parsed["suggestions"]

        task_run.review_result = review_result
        await session.commit()

        if parsed["approved"]:
            await broadcaster.log(
                task_run.id,
                f"Review passed ({len(parsed['issues'])} minor issues, "
                f"{len(parsed['suggestions'])} suggestions)",
                phase="reviewing",
            )
            return

        await broadcaster.log(
            task_run.id,
            f"Review found {len(parsed['issues'])} issues " f"({len(parsed['critical'])} critical)",
            level="warning",
            phase="reviewing",
        )
        for iss in parsed["critical"]:
            await broadcaster.log(
                task_run.id,
                f"  Critical: {iss.get('description', 'no description')[:120]}",
                level="debug",
                phase="reviewing",
            )

        if not will_retry:
            break

        # Store current issues for next iteration comparison
        prev_issues = parsed["issues"]

        # Attempt fix
        retry_count += 1
        task_run.retry_count = retry_count
        await session.commit()

        await broadcaster.log(
            task_run.id,
            f"Attempting auto-fix (retry {retry_count}/{max_retries})",
            phase="reviewing",
        )

        coder_resolved = await services.role_resolver.resolve("coder", session, ws_id)
        coder = coder_resolved.adapter

        async def _review_log(msg: str, level: str = "info") -> None:
            await broadcaster.log(task_run.id, msg, level=level, phase="reviewing")

        await ensure_agent_ready(
            coder, log_fn=_review_log, agent_settings=coder_resolved.agent_settings
        )

        assert fix_instr is not None
        fix_session_id = session_id if getattr(coder, "supports_session", False) else None
        await coder.run_task(
            workspace=task_run.workspace_path,
            instruction=fix_instr,
            log_fn=_review_log,
            session_id=fix_session_id,
        )
        await broadcaster.log(
            task_run.id, "Fix attempt complete, re-running review", phase="reviewing"
        )

    # Exhausted retries — proceed anyway (human will review the PR)
    if retry_count >= max_retries:
        await broadcaster.log(
            task_run.id,
            f"Review issues remain after {max_retries} retries, proceeding to approval",
            level="warning",
            phase="reviewing",
        )


async def _get_diff(
    task_run: TaskRun,
    pr_diff: str | None,
    remote_git: RemoteGitOps | None,
    log_fn,
) -> str:
    """Fetch diff from pre-fetched PR or SSH."""
    if pr_diff:
        await log_fn(f"Using pre-fetched PR diff ({len(pr_diff)} chars)")
        return pr_diff

    assert remote_git is not None
    await log_fn("Fetching git diff from workspace")
    try:
        result = await remote_git.run_git(
            ["diff", f"{task_run.default_branch}...{task_run.branch_name}"],
            cwd=task_run.workspace_path,
        )
        diff_text = result.stdout
        await log_fn(f"Diff: {len(diff_text)} chars")
        return diff_text
    except RuntimeError as exc:
        await log_fn(f"Could not get diff: {exc}")
        return "(diff unavailable)"
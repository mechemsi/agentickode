# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Review retry loop: diff fetching, agent invocation, response parsing, fix attempts."""

import logging
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentInvocation, TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._helpers import (
    ensure_agent_ready,
    get_token_usage,
)
from backend.worker.phases._review_helpers import (
    build_fix_instruction,
    build_review_prompt,
    parse_review_response,
    record_iteration,
    should_retry,
)

logger = logging.getLogger("agentickode.phases.reviewing")

LogFn = Callable[[str], Coroutine[Any, Any, None]]


async def _get_diff(
    task_run: TaskRun,
    pr_diff: str | None,
    remote_git: RemoteGitOps | None,
    log_fn: LogFn,
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


async def run_review_loop(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    *,
    reviewer: Any,
    phase_exec_row: Any | None,
    ws_id: int | None,
    settings_kwargs: dict,
    extra_params: dict,
    system_prompt: str,
    user_template: str,
    temperature: float,
    num_predict: int,
    strictness: str,
    all_files: list[str],
    pr_diff: str | None,
    remote_git: RemoteGitOps | None,
    session_id: str | None,
    agent_mode: str,
    review_result: dict,
) -> None:
    """Execute the review retry loop: review -> parse -> fix -> repeat."""
    retry_count = 0
    max_retries = task_run.max_retries
    prev_issues: list[dict] | None = None

    async def _log_ssh(msg: str) -> None:
        await broadcaster.log(task_run.id, f"  {msg}", level="debug", phase="reviewing")

    while retry_count <= max_retries:
        attempt = retry_count + 1
        await broadcaster.log(
            task_run.id,
            f"Review attempt {attempt}/{max_retries + 1}",
            phase="reviewing",
        )

        # Get diff — skip re-fetching on retries with active session
        if retry_count > 0 and session_id:
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

        will_retry = should_retry(parsed, strictness, retry_count, max_retries)
        fix_instr = build_fix_instruction(parsed, strictness) if will_retry else None

        review_result = record_iteration(
            review_result, attempt, parsed, will_retry, fix_instr, prev_issues
        )

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

        prev_issues = parsed["issues"]

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

    if retry_count >= max_retries:
        await broadcaster.log(
            task_run.id,
            f"Review issues remain after {max_retries} retries, proceeding to approval",
            level="warning",
            phase="reviewing",
        )

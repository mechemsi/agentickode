# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 2: Planning — decompose task into subtasks via role adapter.

Ported from activities.py run_planner_agent + langgraph/agents.py planner prompts.
"""

import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentInvocation, PhaseExecution, TaskRun
from backend.services.container import ServiceContainer
from backend.services.html_to_text import html_to_text
from backend.services.json_extract import extract_json
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._helpers import (
    apply_phase_command_overrides,
    ensure_agent_ready,
    get_agent_mode,
    get_agent_settings_kwargs,
    get_phase_role,
    get_token_usage,
    get_workspace_server_id,
    phase_uses_agent,
)
from backend.worker.phases._prompt_resolver import resolve_prompts

logger = logging.getLogger("agentickode.phases.planning")

PHASE_META = {
    "description": "Decompose task into subtasks via AI agent",
    "default_role": "planner",
    "default_agent_mode": "generate",
}

FALLBACK_SYSTEM_PROMPT = (
    "You are a senior software architect specializing in task decomposition.\n\n"
    "You analyze tasks and break them down into specific, implementable subtasks "
    "ordered by dependency."
)

FALLBACK_USER_TEMPLATE = """## Task
Title: {title}
Description: {description}

## Project Context
{context_text}

## Instructions
1. Analyze the task requirements
2. Break down into specific, implementable subtasks
3. Order subtasks by dependency (what must be done first)
4. Estimate complexity (simple/medium/complex)

Respond in JSON format:
{{
  "subtasks": [
    {{"id": 1, "title": "...", "description": "...", "files_likely_affected": ["..."]}}
  ],
  "estimated_complexity": "simple|medium|complex",
  "notes": "Any important considerations"
}}"""


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> None:
    # Skip if agent is disabled for this phase
    if not phase_uses_agent("planning", phase_config):
        await broadcaster.log(
            task_run.id, "Agent disabled for planning — skipping", phase="planning"
        )
        task_run.planning_result = {"subtasks": [], "agent_skipped": True}
        await session.commit()
        return

    # Get context from init phase
    prev = task_run.planning_result or {}
    context_docs = prev.get("context_docs", [])
    # Cap context docs to ~4000 chars to avoid sending excessive tokens
    if context_docs:
        capped: list[str] = []
        total = 0
        for doc in context_docs:
            if total + len(doc) > 4000 and capped:
                break
            capped.append(doc)
            total += len(doc)
        context_text = "\n\n".join(capped)
    else:
        context_text = "No additional context available."

    # Resolve phase_execution early for agent_override and linking
    pe_result = await session.execute(
        select(PhaseExecution).where(
            PhaseExecution.run_id == task_run.id,
            PhaseExecution.phase_name == "planning",
        )
    )
    phase_exec_row = pe_result.scalar_one_or_none()

    ws_id = await get_workspace_server_id(task_run, session)
    role = get_phase_role("planning", phase_config, phase_exec_row)
    resolved = await services.role_resolver.resolve(role, session, ws_id, phase_name="planning")
    if resolved.is_fallback and resolved.tried:
        tried_msg = ", ".join(resolved.tried)
        await broadcaster.log(
            task_run.id,
            f"⚠ Configured agents failed: {tried_msg} — fell back to Ollama",
            level="warning",
            phase="planning",
        )
    adapter = resolved.adapter
    config = resolved.role_config
    settings_kwargs = get_agent_settings_kwargs(resolved.agent_settings, phase_config)
    apply_phase_command_overrides(adapter, phase_config)

    # Session continuity: start a new session if the adapter supports it
    session_id: str | None = None
    use_sessions = getattr(adapter, "supports_session", False)
    if use_sessions:
        session_id = str(uuid.uuid4())

    system_prompt, user_template, extra_params, project_env_vars = await resolve_prompts(
        config,
        adapter,
        session,
        FALLBACK_SYSTEM_PROMPT,
        FALLBACK_USER_TEMPLATE,
        project_id=task_run.project_id,
        phase_name="planning",
    )
    if project_env_vars:
        existing_env = settings_kwargs.get("environment_vars", {})
        settings_kwargs["environment_vars"] = {**existing_env, **project_env_vars}
    temperature = config.default_temperature if config else 0.3
    num_predict = config.default_num_predict if config else 2048

    user_prompt = user_template.format(
        title=task_run.title,
        description=html_to_text(task_run.description),
        context_text=context_text,
    )

    await broadcaster.log(
        task_run.id,
        f"Sending task to planner via {adapter.provider_name}",
        phase="planning",
        metadata=make_log_metadata("system_prompt", system_prompt_text=system_prompt),
    )
    await broadcaster.log(
        task_run.id,
        f"Task: {task_run.title}",
        level="debug",
        phase="planning",
        metadata=make_log_metadata("prompt", prompt_text=user_prompt),
    )

    # Log callback for SSH visibility in generate()
    async def _log_ssh(msg: str) -> None:
        await broadcaster.log(task_run.id, f"  {msg}", level="debug", phase="planning")

    # Record invocation start
    plan_invocation = AgentInvocation(
        run_id=task_run.id,
        phase_execution_id=phase_exec_row.id if phase_exec_row else None,
        workspace_server_id=ws_id,
        agent_name=adapter.provider_name,
        phase_name="planning",
        subtask_index=None,
        subtask_title=task_run.title,
        prompt_text=user_prompt,
        system_prompt_text=system_prompt,
        prompt_chars=len(user_prompt) + len(system_prompt),
        status="running",
        started_at=datetime.now(UTC),
    )
    session.add(plan_invocation)
    await session.flush()

    agent_mode = get_agent_mode("planning", phase_config)

    async def _phase_log(msg: str, level: str = "info") -> None:
        await broadcaster.log(task_run.id, msg, level=level, phase="planning")

    # Ensure agent binary is accessible (install + worker-user setup if needed)
    await ensure_agent_ready(adapter, log_fn=_phase_log, agent_settings=resolved.agent_settings)

    t0 = time.monotonic()
    if agent_mode == "task":
        # Task mode: run as workspace execution (like coding phase)
        result = await adapter.run_task(
            workspace=task_run.workspace_path,
            instruction=user_prompt,
            system_prompt=system_prompt,
            log_fn=_log_ssh,
            session_id=session_id if session_id else None,
            new_session=bool(session_id),
            **settings_kwargs,
            **extra_params,
        )
        response_text = result.get("output", "")
    else:
        # Generate mode: prompt-based (default for planning)
        generate_kwargs: dict[str, object] = {
            "system_prompt": system_prompt,
            "temperature": temperature,
            "num_predict": num_predict,
            "log_fn": _log_ssh,
            **settings_kwargs,
            **extra_params,
        }
        if session_id:
            generate_kwargs["session_id"] = session_id
            generate_kwargs["new_session"] = True
            generate_kwargs["workspace"] = task_run.workspace_path
        response_text = await adapter.generate(user_prompt, **generate_kwargs)
    elapsed = time.monotonic() - t0

    # Update invocation with results
    plan_invocation.response_text = response_text
    plan_invocation.response_chars = len(response_text)
    plan_invocation.duration_seconds = round(elapsed, 1)
    plan_invocation.completed_at = datetime.now(UTC)
    plan_invocation.status = "success"
    tokens_in, tokens_out, cost, token_source = get_token_usage(
        adapter, adapter.provider_name, plan_invocation.prompt_chars, len(response_text)
    )
    plan_invocation.estimated_tokens_in = tokens_in
    plan_invocation.estimated_tokens_out = tokens_out
    plan_invocation.estimated_cost_usd = cost
    inv_metadata: dict = {"token_source": token_source}
    if session_id:
        plan_invocation.session_id = session_id
        inv_metadata["session_id"] = session_id
    plan_invocation.metadata_ = inv_metadata
    await session.flush()

    elapsed_str = f"{elapsed:.0f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"
    await broadcaster.log(
        task_run.id,
        f"Received response ({len(response_text)} chars) in {elapsed_str}, parsing JSON",
        phase="planning",
        metadata=make_log_metadata("response", response_text=response_text),
    )

    plan_data = extract_json(response_text)

    subtasks = plan_data.get("subtasks", [])
    complexity = plan_data.get("estimated_complexity", "medium")

    planning_result: dict[str, object] = {
        "subtasks": subtasks,
        "estimated_complexity": complexity,
        "context_used": [doc[:100] for doc in context_docs],
    }
    if session_id:
        planning_result["session_id"] = session_id
    task_run.planning_result = planning_result
    await session.commit()

    # Log each subtask title for visibility
    for i, st in enumerate(subtasks):
        await broadcaster.log(
            task_run.id,
            f"  Subtask {i + 1}: {st.get('title', 'untitled')}",
            level="debug",
            phase="planning",
        )

    # Check if plan review is enabled — if so, set coding phase to wait_for_trigger
    enable_review = (phase_config or {}).get("params", {}).get("enable_plan_review", False)
    if not enable_review:
        enable_review = (task_run.task_source_meta or {}).get("enable_plan_review", False)

    if enable_review and subtasks:
        coding_pe_result = await session.execute(
            select(PhaseExecution).where(
                PhaseExecution.run_id == task_run.id,
                PhaseExecution.phase_name == "coding",
            )
        )
        coding_pe = coding_pe_result.scalar_one_or_none()
        if coding_pe:
            coding_pe.trigger_mode = "wait_for_trigger"
            await session.commit()
            logger.info(
                "Run #%d: plan review enabled, coding phase set to wait_for_trigger", task_run.id
            )
            await broadcaster.event(
                task_run.id,
                "plan_review_requested",
                {
                    "run_id": task_run.id,
                    "title": task_run.title,
                    "project_id": task_run.project_id,
                    "subtask_count": len(subtasks),
                },
            )

    await broadcaster.log(
        task_run.id,
        f"Planning complete: {len(subtasks)} subtasks, complexity={complexity}",
        phase="planning",
    )

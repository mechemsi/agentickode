# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Flow-prompt executor (ADR-009).

The run path: workspace setup (task-mode only) -> fetch the flow's data -> a
SINGLE agent call -> finalization. The agent's response is the run outcome,
stored on ``task_runs.coding_results``.

This is the only execution path: ``pipeline.execute_pipeline`` resolves the run's
flow prompt (``pr_review`` for review runs, ``implement`` otherwise) and delegates
here.
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.repositories.flow_prompt_repo import FlowPromptRepository
from backend.services.container import ServiceContainer
from backend.worker.broadcaster import broadcaster
from backend.worker.flow.data_sources import fetch_flow_data
from backend.worker.phases._helpers import (
    close_run_session,
    ensure_agent_ready,
    get_workspace_server_id,
)
from backend.worker.steps.agent_step import run_agent_step

logger = logging.getLogger("agentickode.flow.executor")


def _compose_prompt(prompt: str, data: dict[str, Any]) -> str:
    """Append the fetched data as a context block the agent can read."""
    if not data:
        return prompt
    block = json.dumps(data, indent=2, default=str)
    return f"{prompt}\n\n## Context (fetched by AgenticKode)\n```json\n{block}\n```"


async def _run_phase(name: str, run: TaskRun, session: AsyncSession, services: ServiceContainer):
    """Run a builtin phase module (workspace_setup / init / finalization)."""
    from backend.worker.pipeline import _get_phase_module

    module = _get_phase_module(name)
    if module is None:
        logger.warning("Flow executor: phase module %r not found — skipping", name)
        return
    run.current_phase = name
    await broadcaster.event(run.id, "phase_changed", {"phase": name})
    await module.run(run, session, services, None)


async def execute_flow_prompt(
    run: TaskRun, session: AsyncSession, services: ServiceContainer
) -> None:
    """Execute a run via its bound flow prompt (single agent call)."""
    flow = await FlowPromptRepository(session).get_by_id(run.flow_prompt_id)
    if flow is None:
        run.status = "failed"
        run.error_message = f"flow_prompt_id={run.flow_prompt_id} not found"
        run.completed_at = datetime.now(UTC)
        await session.commit()
        await broadcaster.event(
            run.id, "run_failed", {"run_id": run.id, "error": run.error_message}
        )
        return

    run.status = "running"
    run.started_at = run.started_at or datetime.now(UTC)
    # Resolve a workspace server (the agent CLI needs one to run on) — mirrors the
    # legacy phases, which use get_workspace_server_id rather than the raw column.
    # Falls back to the project's assigned server (e.g. the local platform server).
    if not run.workspace_server_id:
        run.workspace_server_id = await get_workspace_server_id(run, session)
    await session.commit()
    await broadcaster.event(
        run.id,
        "run_started",
        {"status": "running", "title": run.title, "project_id": run.project_id, "flow": flow.name},
    )

    try:
        # Task-mode flows need a checked-out workspace; generate-mode (e.g. PR
        # review on a fetched diff) skips setup entirely.
        if flow.agent_mode == "task":
            await _run_phase("workspace_setup", run, session, services)
            await _run_phase("init", run, session, services)

        data = await fetch_flow_data(run, session, services, flow)
        prompt = _compose_prompt(flow.prompt, data)

        run.current_phase = "agent"
        await broadcaster.event(run.id, "phase_changed", {"phase": "agent"})
        await broadcaster.log(run.id, f"Running flow prompt: {flow.name}", phase="agent")

        # Ensure the CLI agent is installed for the run-as (worker) user before
        # invoking it — parity with the legacy coding/reviewing phases. No-op for
        # root / non-CLI adapters; installs into the worker user's home otherwise.
        resolved = await services.agent_resolver.resolve_agent(
            flow.agent, session, run.workspace_server_id, project_id=run.project_id
        )

        async def _agent_log(msg: str, level: str = "info") -> None:
            await broadcaster.log(run.id, msg, level=level, phase="agent")

        await ensure_agent_ready(
            resolved.adapter, log_fn=_agent_log, agent_settings=resolved.agent_settings
        )

        result = await run_agent_step(
            run,
            session,
            services,
            {"agent": flow.agent, "params": {"prompt": prompt, "mode": flow.agent_mode}},
        )
        run.coding_results = {
            "flow_prompt": flow.name,
            "agent": result.get("agent"),
            "mode": result.get("mode"),
            "response": result.get("response"),
        }
        # PR-review flows: surface the response as review_result so finalization
        # posts it as a PR comment + flips the label (parity with the template path).
        if flow.flow_type == "pr_review":
            resp = result.get("response")
            review_text = resp if isinstance(resp, str) else json.dumps(resp, default=str)
            run.review_result = {
                "summary": review_text,
                "approved": False,
                "issues": [],
                "suggestions": [],
            }
        await session.commit()

        await _run_phase("finalization", run, session, services)

        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        await session.commit()
        await broadcaster.log(run.id, "Flow complete", phase="finalization")
        await broadcaster.event(
            run.id,
            "run_completed",
            {"status": "completed", "run_id": run.id, "title": run.title},
        )
    except Exception as e:
        logger.exception("Flow run #%s failed", run.id)
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = datetime.now(UTC)
        await session.commit()
        await broadcaster.event(
            run.id, "run_failed", {"run_id": run.id, "error": str(e), "title": run.title}
        )
        with contextlib.suppress(Exception):
            await close_run_session(run, session)

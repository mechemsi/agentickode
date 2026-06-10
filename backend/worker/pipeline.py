# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Run dispatcher — every run is a single flow-prompt agent call (ADR-009).

The legacy multi-step ``WorkflowTemplate`` / ``PhaseExecution`` engine
(composable bash+agent steps, autonomous phase sequences, comparison mode) was
removed in Phase 5. ``execute_pipeline`` now resolves the run's flow prompt
(``pr_review`` for review runs, ``implement`` otherwise) and hands off to the
flow executor, which runs builtin ``workspace_setup`` → ``init`` → fetch data →
a single agent call → ``finalization``.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.repositories.flow_prompt_repo import FlowPromptRepository
from backend.services.container import ServiceContainer
from backend.worker.broadcaster import broadcaster
from backend.worker.phases.registry import discover_phases

logger = logging.getLogger("agentickode.pipeline")

# Populated lazily from the phase registry. The flow executor resolves builtin
# phase modules (workspace_setup / init / finalization / pr_fetch) by name via
# _get_phase_module.
_phase_modules: dict | None = None


def _get_phase_modules() -> dict:
    global _phase_modules
    if _phase_modules is None:
        _phase_modules = {name: info.module for name, info in discover_phases().items()}
    return _phase_modules


def _get_phase_module(phase_name: str):
    """Resolve a builtin phase module by name from the registry."""
    return _get_phase_modules().get(phase_name)


def _flow_type_for(run: TaskRun) -> str:
    """PR-review runs use the ``pr_review`` flow; everything else ``implement``."""
    return "pr_review" if (run.task_source_meta or {}).get("review_mode") else "implement"


async def execute_pipeline(run: TaskRun, session: AsyncSession, services: ServiceContainer) -> None:
    """Execute a run as a single flow-prompt agent call (ADR-009).

    Resolves the run's flow prompt — the explicitly-bound ``flow_prompt_id`` if
    set (e.g. by the PR-review poller/webhook), otherwise the default for the
    run's flow type — and delegates to the flow executor.
    """
    if not run.flow_prompt_id:
        flow_type = _flow_type_for(run)
        flow = await FlowPromptRepository(session).get_by_flow_type(flow_type)
        if flow is None:
            run.status = "failed"
            run.error_message = f"No '{flow_type}' flow prompt is configured"
            run.completed_at = datetime.now(UTC)
            await session.commit()
            await broadcaster.event(
                run.id, "run_failed", {"run_id": run.id, "error": run.error_message}
            )
            return
        run.flow_prompt_id = flow.id
        await session.commit()

    from backend.worker.flow.executor import execute_flow_prompt

    await execute_flow_prompt(run, session, services)

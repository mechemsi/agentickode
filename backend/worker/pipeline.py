# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase sequencer — event-driven pipeline with per-phase status tracking.

Each phase has its own PhaseExecution row with status lifecycle:
pending → running → completed/failed/waiting
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PhaseExecution, TaskRun
from backend.repositories.phase_execution_repo import PhaseExecutionRepository
from backend.repositories.workflow_template_repo import WorkflowTemplateRepository
from backend.services.container import ServiceContainer
from backend.services.workspace.ssh_service import SSHCommandError
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._helpers import close_run_session
from backend.worker.phases.registry import discover_phases

logger = logging.getLogger("agentickode.pipeline")

PHASE_NAMES = [
    "workspace_setup",
    "init",
    "planning",
    "coding",
    "testing",
    "reviewing",
    "approval",
    "finalization",
]

# Populated lazily from the phase registry.
_phase_modules: dict | None = None


def _get_phase_modules() -> dict:
    global _phase_modules
    if _phase_modules is None:
        _phase_modules = {name: info.module for name, info in discover_phases().items()}
    return _phase_modules


# Legacy JSONB column mapping: phase_name → TaskRun attribute
_LEGACY_RESULT_MAP = {
    "workspace_setup": "workspace_result",
    "planning": "planning_result",
    "coding": "coding_results",
    "testing": "test_results",
    "reviewing": "review_result",
}


def _get_phase_module(phase_name: str):
    """Resolve a phase module by name from the registry."""
    return _get_phase_modules().get(phase_name)


async def _resolve_workflow_phases(run: TaskRun, session: AsyncSession) -> list[dict[str, Any]]:
    """Resolve which phases to run based on workflow templates and task labels.

    Priority:
    1. Explicit workflow_template_id on the run
    2. Label-based matching
    3. Default template
    4. Hardcoded PHASE_NAMES fallback
    """
    try:
        repo = WorkflowTemplateRepository(session)
        template = None

        # 1. Explicit workflow_template_id takes priority
        if run.workflow_template_id:
            template = await repo.get_by_id(run.workflow_template_id)

        # 2. Try label-based matching
        if not template:
            labels = (run.task_source_meta or {}).get("labels", [])
            template = await repo.match_labels(labels) if labels else await repo.get_default()

        if template and template.phases:
            # Record which template was used (if not already set)
            if not run.workflow_template_id:
                run.workflow_template_id = template.id
            phases = cast(list[dict[str, Any]], template.phases)
            return [p for p in phases if p.get("enabled", True)]
    except Exception:
        logger.warning("Failed to resolve workflow template, using defaults", exc_info=True)

    return [{"phase_name": name, "enabled": True} for name in PHASE_NAMES]


async def _ensure_phase_executions(run: TaskRun, session: AsyncSession) -> list[PhaseExecution]:
    """Create PhaseExecution rows if they don't exist for this run."""
    repo = PhaseExecutionRepository(session)
    existing = await repo.get_by_run(run.id)
    if existing:
        return existing

    workflow_phases = await _resolve_workflow_phases(run, session)
    return await repo.create_for_run(run.id, workflow_phases)


async def execute_pipeline(run: TaskRun, session: AsyncSession, services: ServiceContainer) -> None:
    """Execute the pipeline phase-by-phase using PhaseExecution rows."""
    run.status = "running"
    run.started_at = run.started_at or datetime.now(UTC)
    await session.commit()
    await broadcaster.event(
        run.id,
        "run_started",
        {"status": "running", "title": run.title, "project_id": run.project_id},
    )

    await _ensure_phase_executions(run, session)
    pe_repo = PhaseExecutionRepository(session)

    while True:
        phase_exec = await pe_repo.get_next_pending(run.id)
        if phase_exec is None:
            break

        phase_name = phase_exec.phase_name
        phase_mod = _get_phase_module(phase_name)
        if phase_mod is None:
            logger.warning("Unknown phase '%s', skipping", phase_name)
            await pe_repo.update_status(phase_exec, "skipped")
            continue

        # Check if run was cancelled externally
        await session.refresh(run)
        if run.status == "cancelled":
            await broadcaster.log(run.id, "Run was cancelled", level="warning", phase=phase_name)
            await close_run_session(run, session)
            return

        # PRE-execute trigger_mode check
        if phase_exec.trigger_mode == "wait_for_trigger":
            await pe_repo.update_status(phase_exec, "waiting")
            run.status = "waiting_for_trigger"
            run.current_phase = phase_name
            await session.commit()
            await broadcaster.log(
                run.id, f"Waiting for external trigger: {phase_name}", phase=phase_name
            )
            await broadcaster.event(
                run.id, "phase_waiting", {"phase": phase_name, "trigger_mode": "wait_for_trigger"}
            )
            return

        # Execute phase
        run.current_phase = phase_name
        run.phase_started_at = datetime.now(UTC)
        await pe_repo.update_status(phase_exec, "running")
        await session.commit()
        await broadcaster.event(run.id, "phase_changed", {"phase": phase_name})
        await broadcaster.log(run.id, f"Starting phase: {phase_name}", phase=phase_name)

        try:
            result = await phase_mod.run(
                run, session, services, phase_config=phase_exec.phase_config
            )
        except Exception as e:
            logger.exception(f"Run #{run.id} failed in {phase_name}")

            # Provide user-friendly error messages for common failures
            if isinstance(e, SSHCommandError):
                user_msg = f"SSH error on {e.hostname}: {e}"
            else:
                user_msg = str(e)

            phase_exec.retry_count += 1
            if phase_exec.retry_count < phase_exec.max_retries:
                await broadcaster.log(
                    run.id,
                    f"Phase error (will retry {phase_exec.retry_count}/{phase_exec.max_retries}): "
                    f"{user_msg}",
                    level="warning",
                    phase=phase_name,
                )
                await pe_repo.update_status(phase_exec, "pending", error_message=user_msg)
                continue
            await pe_repo.update_status(phase_exec, "failed", error_message=user_msg)
            run.status = "failed"
            run.error_message = f"{phase_name}: {user_msg}"
            run.completed_at = datetime.now(UTC)
            await session.commit()
            await broadcaster.log(
                run.id, f"Phase failed: {user_msg}", level="error", phase=phase_name
            )
            await broadcaster.event(run.id, "phase_failed", {"phase": phase_name, "error": str(e)})
            await broadcaster.event(
                run.id,
                "run_failed",
                {
                    "phase": phase_name,
                    "error": str(e),
                    "run_id": run.id,
                    "title": run.title,
                    "project_id": run.project_id,
                },
            )

            # Close any agent session to release locks
            await close_run_session(run, session)

            # Notify task source on failure if configured
            if phase_exec.notify_source and services.task_source_updater:
                await services.task_source_updater.notify(
                    task_source=run.task_source,
                    task_source_meta=run.task_source_meta or {},
                    phase_name=phase_name,
                    status="failed",
                    run_id=run.id,
                )

            # Fire webhook callbacks on failure
            if services.webhook_callbacks:
                await services.webhook_callbacks.fire(
                    session=session,
                    run_id=run.id,
                    event="phase_failed",
                    payload={"phase": phase_name, "error": str(e)},
                )
            return

        # Phase succeeded
        result_data = result if isinstance(result, dict) else None
        await pe_repo.update_status(phase_exec, "completed", result=result_data)

        # Populate legacy JSONB columns for backward compat
        legacy_attr = _LEGACY_RESULT_MAP.get(phase_name)
        if legacy_attr and result_data:
            setattr(run, legacy_attr, result_data)

        await broadcaster.log(run.id, f"Phase complete: {phase_name}", phase=phase_name)
        await broadcaster.event(run.id, "phase_completed", {"phase": phase_name})

        # Notify task source if configured
        if phase_exec.notify_source and services.task_source_updater:
            await services.task_source_updater.notify(
                task_source=run.task_source,
                task_source_meta=run.task_source_meta or {},
                phase_name=phase_name,
                status="completed",
                run_id=run.id,
                pr_url=run.pr_url,
            )

        # Fire webhook callbacks
        if services.webhook_callbacks:
            await services.webhook_callbacks.fire(
                session=session,
                run_id=run.id,
                event="phase_completed",
                payload={"phase": phase_name, "result": result_data},
            )

        # POST-execute trigger_mode check: approval parking
        if phase_exec.trigger_mode == "wait_for_approval":
            await pe_repo.update_status(phase_exec, "waiting")
            run.status = "awaiting_approval"
            run.approval_requested_at = datetime.now(UTC)
            await session.commit()
            await broadcaster.log(run.id, "Awaiting human approval", phase=phase_name)
            await broadcaster.event(
                run.id, "phase_waiting", {"phase": phase_name, "trigger_mode": "wait_for_approval"}
            )
            return

        await session.commit()

        # Optional delay between phases (per-phase config overrides global)
        from backend.config import settings

        delay = (phase_exec.phase_config or {}).get("delay_seconds", settings.phase_delay_seconds)
        if delay and delay > 0:
            await broadcaster.log(
                run.id, f"Waiting {delay}s before next phase", level="debug", phase=phase_name
            )
            await asyncio.sleep(delay)

    # All phases completed
    run.status = "completed"
    run.completed_at = datetime.now(UTC)
    await session.commit()
    await broadcaster.log(run.id, "Pipeline complete", phase="finalization")
    duration_seconds = None
    if run.started_at and run.completed_at:
        with contextlib.suppress(TypeError):
            duration_seconds = (run.completed_at - run.started_at).total_seconds()
    await broadcaster.event(
        run.id,
        "run_completed",
        {
            "status": "completed",
            "run_id": run.id,
            "title": run.title,
            "project_id": run.project_id,
            "pr_url": getattr(run, "pr_url", None) or "",
            "duration_seconds": duration_seconds,
        },
    )

    # Fire webhook callbacks on run completion
    if services.webhook_callbacks:
        await services.webhook_callbacks.fire(
            session=session,
            run_id=run.id,
            event="run_completed",
            payload={"status": "completed"},
        )

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
from backend.worker.steps import agent_step as _agent_step_mod
from backend.worker.steps import bash_step as _bash_step_mod

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

# Phase sequences for each execution mode.
# "structured" uses the default PHASE_NAMES above (resolved via workflow templates).
# Other modes bypass workflow templates and use these fixed sequences.
_AUTONOMOUS_PHASE_SEQUENCES: dict[str, list[str]] = {
    "autonomous": ["workspace_setup", "agent_loop", "approval", "finalization"],
    "hybrid": ["workspace_setup", "init", "agent_loop", "approval", "finalization"],
    "multi_agent": ["workspace_setup", "agent_loop_multi", "approval", "finalization"],
}

# Populated lazily from the phase registry.
_phase_modules: dict | None = None


def _get_phase_modules() -> dict:
    global _phase_modules
    if _phase_modules is None:
        _phase_modules = {name: info.module for name, info in discover_phases().items()}
    return _phase_modules


# Legacy JSONB column mapping: phase_name → TaskRun attribute.
#
# Deprecated in 0.5.0 (ADR-007): we no longer write to these columns on phase
# completion — the authoritative result is ``PhaseExecution.result``. The map
# is retained for one release so existing code paths that READ these columns
# (run detail view fallback, analytics queries) continue to work for runs
# that completed before the cut-over. The columns themselves will be
# dropped in 0.7.0; the read fallbacks should be removed in 0.6.0.
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


class UnknownStepKindError(Exception):
    """Raised when ``phase_config['kind']`` doesn't match a known dispatcher.

    Distinct from generic exceptions raised inside a step runner so the
    pipeline can mark the phase ``"skipped"`` rather than retry-and-fail
    the whole run when a template is misconfigured.
    """


async def _dispatch_step(
    run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_exec: PhaseExecution,
) -> dict[str, Any] | str | None:
    """Dispatch a phase execution to its runner based on ``phase_config['kind']``.

    Returns whatever the runner returns. Raises ``UnknownStepKindError`` for
    unknown kinds or missing legacy modules; the caller marks the phase
    ``"skipped"`` on that signal rather than failing the run.

    Step modules are accessed via the bound module references so that tests
    can ``monkeypatch.setattr`` the functions on their source modules.
    """
    cfg = phase_exec.phase_config or {}
    kind = cfg.get("kind", "legacy_phase")

    if kind == "bash":
        return await _bash_step_mod.run_bash_step(run, session, services, cfg)

    if kind == "agent":
        return await _agent_step_mod.run_agent_step(run, session, services, cfg)

    if kind == "legacy_phase":
        phase_mod = _get_phase_module(phase_exec.phase_name)
        if phase_mod is None:
            raise UnknownStepKindError(f"Unknown legacy phase: {phase_exec.phase_name}")
        return await phase_mod.run(run, session, services, phase_config=cfg)

    raise UnknownStepKindError(f"Unknown step kind: {kind!r} for phase {phase_exec.phase_name!r}")


async def _get_project_execution_mode(run: TaskRun, session: AsyncSession) -> str:
    """Return the execution_mode from project autonomy_config, defaulting to 'structured'."""
    try:
        from sqlalchemy import select as sa_select

        from backend.models import ProjectConfig

        result = await session.execute(
            sa_select(ProjectConfig.autonomy_config).where(
                ProjectConfig.project_id == run.project_id
            )
        )
        config = result.scalar_one_or_none() or {}
        return (
            config.get("execution_mode", "structured") if isinstance(config, dict) else "structured"
        )
    except Exception:
        logger.debug("Could not read execution_mode for run #%s", run.id, exc_info=True)
        return "structured"


async def _resolve_workflow_phases(run: TaskRun, session: AsyncSession) -> list[dict[str, Any]]:
    """Resolve which phases to run based on execution_mode, workflow templates, and task labels.

    Priority:
    1. autonomy_config.execution_mode (autonomous/hybrid/multi_agent) → fixed sequence
    2. Explicit workflow_template_id on the run
    3. Label-based matching
    4. Default template
    5. Hardcoded PHASE_NAMES fallback
    """
    # 0. PR-review runs are bound to the pr-review template and must NEVER be
    # diverted into a project's autonomous/coder pipeline — they have no checkout,
    # so running a coder/agent_loop against them is wrong (and destructive). The
    # explicit binding wins over execution_mode; if the template can't be resolved
    # (binding lost or never seeded) we fail loudly rather than fall through.
    meta = run.task_source_meta or {}
    if meta.get("review_mode"):
        repo = WorkflowTemplateRepository(session)
        template = None
        if run.workflow_template_id:
            template = await repo.get_by_id(run.workflow_template_id)
        if not template:
            template = await repo.get_by_name("pr-review")
        if not template or not template.phases:
            raise RuntimeError(
                f"PR-review run #{run.id} could not resolve a pr-review workflow template "
                f"(workflow_template_id={run.workflow_template_id})"
            )
        if not run.workflow_template_id:
            run.workflow_template_id = template.id
        review_phases = cast(list[dict[str, Any]], template.phases)
        return [p for p in review_phases if p.get("enabled", True)]

    # 1. Check execution mode — autonomous modes use fixed sequences
    execution_mode = await _get_project_execution_mode(run, session)
    if execution_mode in _AUTONOMOUS_PHASE_SEQUENCES:
        phase_names = _AUTONOMOUS_PHASE_SEQUENCES[execution_mode]
        logger.info(
            "Run #%s using execution_mode=%s: phases=%s",
            run.id,
            execution_mode,
            phase_names,
        )
        return [{"phase_name": name, "enabled": True} for name in phase_names]

    # 2-5. Structured mode: resolve via workflow templates
    try:
        repo = WorkflowTemplateRepository(session)
        template = None

        # 2. Explicit workflow_template_id takes priority
        if run.workflow_template_id:
            template = await repo.get_by_id(run.workflow_template_id)

        # 3. Try label-based matching
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


async def _skip_phases_for_consolidated(
    run: TaskRun,
    session: AsyncSession,
    pe_repo: PhaseExecutionRepository,
    services: ServiceContainer,
) -> None:
    """When coding phase uses consolidated mode, skip planning and reviewing.

    Consolidated mode means the agent handles plan + code + review in a single
    invocation, so separate planning and reviewing phases are redundant.

    Resolution priority:
    1. Explicit in coding phase_config params
    2. Run-level phase_overrides in task_source_meta
    3. Agent's consolidated_default from DB
    """
    phases = await pe_repo.get_by_run(run.id)
    coding_pe = next((p for p in phases if p.phase_name == "coding"), None)
    if not coding_pe:
        return

    # 1. Check coding phase_config params
    params = (coding_pe.phase_config or {}).get("params", {})
    consolidated = params.get("consolidated")

    # 2. Check run-level phase_overrides
    if consolidated is None:
        meta_overrides = (run.task_source_meta or {}).get("phase_overrides", {})
        coding_override = meta_overrides.get("coding", {})
        consolidated = coding_override.get("params", {}).get("consolidated")

    # 3. Check agent's consolidated_default
    if consolidated is None:
        try:
            from backend.worker.phases._helpers import get_phase_agent, get_workspace_server_id

            ws_id = await get_workspace_server_id(run, session)
            agent_name = get_phase_agent("coding", coding_pe.phase_config, coding_pe)
            resolved = await services.agent_resolver.resolve_agent(
                agent_name, session, ws_id, project_id=run.project_id
            )
            if resolved.agent_settings:
                val = getattr(resolved.agent_settings, "consolidated_default", None)
                if isinstance(val, bool):
                    consolidated = val
        except Exception:
            logger.debug("Could not resolve agent for consolidated check", exc_info=True)

    if not consolidated:
        return

    skip_phases = {"planning", "reviewing"}
    for pe in phases:
        if pe.phase_name in skip_phases and pe.status == "pending":
            await pe_repo.update_status(pe, "skipped")
            await broadcaster.log(
                run.id,
                f"Skipped {pe.phase_name} — consolidated mode handles it in coding phase",
                phase=pe.phase_name,
            )
    await session.commit()


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

    # Auto-skip planning + reviewing when coding is in consolidated mode
    await _skip_phases_for_consolidated(run, session, pe_repo, services)

    while True:
        phase_exec = await pe_repo.get_next_pending(run.id)
        if phase_exec is None:
            break

        phase_name = phase_exec.phase_name

        # Legacy-phase fast skip: if kind=='legacy_phase' (default) AND the
        # named module doesn't exist, skip with a warning. Non-legacy kinds
        # (bash/agent/...) intentionally bypass this check.
        cfg = phase_exec.phase_config or {}
        if (
            cfg.get("kind", "legacy_phase") == "legacy_phase"
            and _get_phase_module(phase_name) is None
        ):
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
            result = await _dispatch_step(run, session, services, phase_exec)
        except UnknownStepKindError as e:
            # Unknown kind / unknown legacy phase fell through — skip the
            # phase (don't fail the run) so a misconfigured template doesn't
            # take down an otherwise-valid pipeline.
            logger.warning("Cannot dispatch phase '%s': %s", phase_name, e)
            await pe_repo.update_status(phase_exec, "skipped", error_message=str(e))
            await session.commit()
            continue
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

        # Per ADR-007 we no longer mirror result_data into the legacy
        # TaskRun.*_result columns — PhaseExecution.result is authoritative.
        # Read-path fallbacks for old runs stay in place until 0.6.0.

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

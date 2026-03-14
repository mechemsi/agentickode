# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Run state-transition endpoints: approve, reject, retry, restart, cancel, terminal-action."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ProjectConfig
from backend.repositories.phase_execution_repo import PhaseExecutionRepository
from backend.repositories.task_run_repo import TaskRunRepository
from backend.schemas import RejectRequest, TerminalActionRequest

logger = logging.getLogger("agentickode.runs")
router = APIRouter(tags=["runs"])


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: int, db: AsyncSession = Depends(get_db)):
    repo = TaskRunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "awaiting_approval":
        raise HTTPException(400, f"Run is {run.status}, not awaiting_approval")
    run.approved = True
    run.updated_at = datetime.now(UTC)
    await repo.commit()
    logger.info(f"Run #{run_id} approved")
    return {"status": "approved"}


@router.post("/runs/{run_id}/reject")
async def reject_run(
    run_id: int,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = TaskRunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "awaiting_approval":
        raise HTTPException(400, f"Run is {run.status}, not awaiting_approval")
    run.approved = False
    run.rejection_reason = body.reason
    run.updated_at = datetime.now(UTC)
    await repo.commit()
    logger.info(f"Run #{run_id} rejected: {body.reason}")
    return {"status": "rejected"}


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: int, db: AsyncSession = Depends(get_db)):
    repo = TaskRunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status not in ("failed", "cancelled", "timeout"):
        raise HTTPException(400, f"Can only retry failed/cancelled/timeout runs, got {run.status}")
    run.status = "pending"
    run.error_message = None
    run.approved = None
    run.rejection_reason = None
    run.retry_count = 0
    run.updated_at = datetime.now(UTC)

    # Reset failed/waiting phase executions back to pending
    pe_repo = PhaseExecutionRepository(db)
    phases = await pe_repo.get_by_run(run_id)
    for phase in phases:
        if phase.status in ("failed", "waiting", "cancelled"):
            phase.status = "pending"
            phase.error_message = None
            phase.retry_count = 0

    await db.commit()
    logger.info(f"Run #{run_id} retried")
    return {"status": "retried"}


@router.post("/runs/{run_id}/restart")
async def restart_run(run_id: int, db: AsyncSession = Depends(get_db)):
    """Fully restart a run from scratch -- resets all phases, results, and workspace path."""
    repo = TaskRunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status in ("pending", "running"):
        raise HTTPException(400, f"Run is {run.status}, cancel it first")

    # Re-derive the original workspace_path from the project config
    project = await db.get(ProjectConfig, run.project_id)
    original_ws_path = (project.workspace_path if project else None) or run.repo_name
    run.workspace_path = original_ws_path

    run.status = "pending"
    run.error_message = None
    run.approved = None
    run.rejection_reason = None
    run.retry_count = 0
    run.current_phase = None
    run.started_at = None
    run.completed_at = None
    run.workspace_result = None
    run.planning_result = None
    run.coding_results = None
    run.test_results = None
    run.review_result = None
    run.updated_at = datetime.now(UTC)

    # Reset ALL phase executions back to pending
    pe_repo = PhaseExecutionRepository(db)
    phases = await pe_repo.get_by_run(run_id)
    for phase in phases:
        phase.status = "pending"
        phase.error_message = None
        phase.retry_count = 0
        phase.started_at = None
        phase.completed_at = None
        phase.result = None

    await db.commit()
    logger.info(f"Run #{run_id} fully restarted")
    return {"status": "restarted"}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: int, db: AsyncSession = Depends(get_db)):
    repo = TaskRunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status in ("completed", "cancelled"):
        raise HTTPException(400, f"Run is already {run.status}")
    run.status = "cancelled"
    run.completed_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    await repo.commit()
    logger.info(f"Run #{run_id} cancelled")
    return {"status": "cancelled"}


TERMINAL_ELIGIBLE_STATUSES = {
    "completed",
    "failed",
    "awaiting_approval",
    "timeout",
    "cancelled",
    "waiting_for_trigger",
}


@router.post("/runs/{run_id}/terminal-action")
async def run_terminal_action(
    run_id: int,
    body: TerminalActionRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = TaskRunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status not in TERMINAL_ELIGIBLE_STATUSES:
        raise HTTPException(400, f"Run is {run.status}, not eligible for terminal action")
    if body.action not in ("continue", "pause", "complete"):
        raise HTTPException(400, f"Invalid action: {body.action}")

    if body.action == "continue":
        run.status = "pending"
        run.updated_at = datetime.now(UTC)
    elif body.action == "complete":
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.updated_at = datetime.now(UTC)
    # "pause" is a no-op -- leave run in current status

    await repo.commit()
    logger.info(f"Run #{run_id} terminal action: {body.action}")
    return {"status": body.action}

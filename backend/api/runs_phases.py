# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase management, telemetry, and comparison endpoints for task runs."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.phase_execution_repo import PhaseExecutionRepository
from backend.repositories.task_run_repo import TaskRunRepository
from backend.schemas import (
    AdvancePhaseRequest,
    AgentInvocationDetail,
    AgentInvocationOut,
    PhaseExecutionOut,
    PickWinnerRequest,
    PlanReviewRequest,
)

logger = logging.getLogger("agentickode.runs")
router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}/phases", response_model=list[PhaseExecutionOut])
async def list_run_phases(run_id: int, db: AsyncSession = Depends(get_db)):
    repo = TaskRunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    pe_repo = PhaseExecutionRepository(db)
    return await pe_repo.get_by_run(run_id)


@router.post("/runs/{run_id}/phases/{phase_name}/advance")
async def advance_phase(
    run_id: int,
    phase_name: str,
    body: AdvancePhaseRequest = AdvancePhaseRequest(),
    db: AsyncSession = Depends(get_db),
):
    run_repo = TaskRunRepository(db)
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    pe_repo = PhaseExecutionRepository(db)
    phase_exec = await pe_repo.get_by_run_and_phase(run_id, phase_name)
    if not phase_exec:
        raise HTTPException(404, f"Phase '{phase_name}' not found for run #{run_id}")

    if phase_exec.status != "waiting" and not body.force:
        raise HTTPException(400, f"Phase is {phase_exec.status}, not waiting")

    phase_exec.status = "pending"
    run.status = "pending"
    run.updated_at = datetime.now(UTC)
    await db.commit()
    logger.info(f"Advanced phase '{phase_name}' for run #{run_id}")
    return {"status": "advanced", "phase": phase_name}


@router.post("/runs/{run_id}/plan-review")
async def plan_review(
    run_id: int,
    body: PlanReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a plan review before coding begins."""
    repo = TaskRunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "waiting_for_trigger":
        raise HTTPException(400, f"Run is {run.status}, not waiting_for_trigger")

    pe_repo = PhaseExecutionRepository(db)
    coding_phase = await pe_repo.get_by_run_and_phase(run_id, "coding")
    if not coding_phase or coding_phase.status != "waiting":
        raise HTTPException(400, "Coding phase is not in waiting state")

    if body.action == "approve":
        # Optionally update planning_result with modified subtasks
        if body.modified_subtasks is not None:
            planning_result: dict = {**(run.planning_result or {})}
            planning_result["subtasks"] = body.modified_subtasks
            run.planning_result = planning_result
        coding_phase.status = "pending"
        coding_phase.trigger_mode = "auto"
        run.status = "pending"
        run.updated_at = datetime.now(UTC)
        await db.commit()
        logger.info(f"Run #{run_id} plan approved, coding resumed")
        return {"status": "approved"}

    if body.action == "reject":
        reason = body.rejection_reason or "Plan rejected"
        coding_phase.status = "failed"
        coding_phase.error_message = reason
        run.status = "failed"
        run.error_message = f"Plan rejected: {reason}"
        run.completed_at = datetime.now(UTC)
        run.updated_at = datetime.now(UTC)
        await db.commit()
        logger.info(f"Run #{run_id} plan rejected: {reason}")
        return {"status": "rejected"}

    raise HTTPException(400, f"Invalid action: {body.action}")


@router.get("/runs/{run_id}/invocations", response_model=list[AgentInvocationOut])
async def list_run_invocations(
    run_id: int,
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    from backend.models import AgentInvocation

    stmt = select(AgentInvocation).where(AgentInvocation.run_id == run_id)
    if session_id:
        stmt = stmt.where(AgentInvocation.session_id == session_id)
    result = await db.execute(stmt.order_by(AgentInvocation.started_at))
    return result.scalars().all()


@router.get("/runs/{run_id}/invocations/{invocation_id}", response_model=AgentInvocationDetail)
async def get_invocation_detail(
    run_id: int, invocation_id: int, db: AsyncSession = Depends(get_db)
):
    from backend.models import AgentInvocation

    result = await db.execute(
        select(AgentInvocation).where(
            AgentInvocation.id == invocation_id, AgentInvocation.run_id == run_id
        )
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(404, "Invocation not found")
    return inv


@router.post("/runs/{run_id}/comparison/pick-winner")
async def pick_comparison_winner(
    run_id: int,
    body: PickWinnerRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = TaskRunRepository(db)
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    coding: dict = {**(run.coding_results or {})}
    if not coding.get("comparison_mode"):
        raise HTTPException(400, "Run is not in comparison mode")

    if body.winner not in ("a", "b"):
        raise HTTPException(400, "winner must be 'a' or 'b'")

    agents = coding.get("agents", {})
    if body.winner not in agents:
        raise HTTPException(400, f"No agent data for '{body.winner}'")

    # Update winner in coding_results
    coding["winner"] = body.winner
    run.coding_results = coding
    run.updated_at = datetime.now(UTC)
    await db.commit()

    winner_info = agents[body.winner]
    logger.info(
        "Run #%d comparison winner: %s (%s)",
        run_id,
        body.winner,
        winner_info.get("agent_name"),
    )
    return {
        "status": "winner_picked",
        "winner": body.winner,
        "agent_name": winner_info.get("agent_name"),
        "branch": winner_info.get("branch"),
    }

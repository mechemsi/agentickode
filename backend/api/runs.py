# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Task run CRUD + approve/reject/retry/cancel + phase advance."""

import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ProjectConfig, TaskRun
from backend.repositories.phase_execution_repo import PhaseExecutionRepository
from backend.repositories.task_run_repo import TaskRunRepository
from backend.schemas import (
    AdvancePhaseRequest,
    AgentInvocationDetail,
    AgentInvocationOut,
    CreateRunRequest,
    CreateRunResponse,
    PaginatedRunsResponse,
    PhaseExecutionOut,
    PickWinnerRequest,
    PlanReviewRequest,
    RejectRequest,
    TaskRunDetail,
    TerminalActionRequest,
)

logger = logging.getLogger("agentickode.runs")
router = APIRouter(tags=["runs"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> TaskRunRepository:
    return TaskRunRepository(db)


@router.get("/runs", response_model=PaginatedRunsResponse)
async def list_runs(
    status: str | None = None,
    project_id: str | None = None,
    search: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|title|status)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repo: TaskRunRepository = Depends(_get_repo),
):
    items, total = await repo.list_runs(
        status=status,
        project_id=project_id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return PaginatedRunsResponse(items=items, total=total, offset=offset, limit=limit)


@router.post("/runs", response_model=CreateRunResponse, status_code=201)
async def create_run(req: CreateRunRequest, db: AsyncSession = Depends(get_db)):
    project = await db.get(ProjectConfig, req.project_id)
    if not project:
        raise HTTPException(404, f"Project {req.project_id} not found")

    ts = int(time.time())
    slug = project.project_slug or project.repo_name
    branch_name = f"agentickode/{slug}/{ts}"

    ws_server_id = req.workspace_server_id or project.workspace_server_id
    workspace_path = project.workspace_path or project.repo_name

    # Build task_source_meta upfront so we never mutate Column objects
    meta: dict = {"labels": req.labels}
    if req.agent_override:
        meta["agent_override"] = req.agent_override
    if req.phase_overrides:
        meta["phase_overrides"] = req.phase_overrides
    if ws_server_id is not None:
        meta["workspace_server_id"] = ws_server_id
    if req.issue_number is not None:
        meta["issue_number"] = req.issue_number
    if req.issue_url:
        meta["issue_url"] = req.issue_url
    if req.skip_schedule:
        meta["skip_schedule"] = True

    run = TaskRun(
        task_id=f"manual-{ts}",
        project_id=req.project_id,
        title=req.title,
        description=req.description,
        branch_name=branch_name,
        workspace_path=workspace_path,
        repo_owner=project.repo_owner,
        repo_name=project.repo_name,
        default_branch=project.default_branch,
        task_source="manual",
        git_provider=project.git_provider,
        task_source_meta=meta,
        run_type=req.run_type,
        status="pending",
        workflow_template_id=req.workflow_template_id,
        workspace_config=project.workspace_config,
    )

    db.add(run)
    await db.flush()
    await db.commit()
    await db.refresh(run)

    logger.info(f"Created manual run #{run.id} for project {req.project_id}")
    return CreateRunResponse(
        id=run.id,
        status=run.status,
        title=run.title,
        project_id=run.project_id,
        branch_name=run.branch_name,
    )


@router.get("/runs/{run_id}", response_model=TaskRunDetail)
async def get_run(run_id: int, repo: TaskRunRepository = Depends(_get_repo)):
    run = await repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


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
    """Fully restart a run from scratch — resets all phases, results, and workspace path."""
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
async def cancel_run(run_id: int, repo: TaskRunRepository = Depends(_get_repo)):
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
    # "pause" is a no-op — leave run in current status

    await repo.commit()
    logger.info(f"Run #{run_id} terminal action: {body.action}")
    return {"status": body.action}


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


@router.get("/stats")
async def get_stats(repo: TaskRunRepository = Depends(_get_repo)):
    return await repo.get_stats()

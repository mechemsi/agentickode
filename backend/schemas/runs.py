# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TaskRunOut(BaseModel):
    id: int
    run_type: str
    task_id: str
    project_id: str
    title: str
    description: str
    branch_name: str
    status: str
    current_phase: str | None
    retry_count: int
    error_message: str | None
    pr_url: str | None
    approved: bool | None
    rejection_reason: str | None
    parent_run_id: int | None = None
    workflow_template_id: int | None = None
    total_cost_usd: float | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class PhaseExecutionOut(BaseModel):
    id: int
    run_id: int
    phase_name: str
    order_index: int
    trigger_mode: str
    status: str
    result: dict[str, Any] | None
    error_message: str | None
    retry_count: int
    max_retries: int
    agent_override: str | None
    notify_source: bool
    phase_config: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskRunDetail(TaskRunOut):
    max_retries: int
    workspace_path: str
    repo_owner: str
    repo_name: str
    default_branch: str
    task_source: str
    git_provider: str
    task_source_meta: dict[str, Any]
    use_claude_api: bool
    workspace_config: dict[str, Any] | None
    workspace_result: dict[str, Any] | None
    planning_result: dict[str, Any] | None
    coding_results: dict[str, Any] | None
    test_results: dict[str, Any] | None
    review_result: dict[str, Any] | None
    approval_requested_at: datetime | None
    phase_started_at: datetime | None
    phase_executions: list[PhaseExecutionOut] = []


class PaginatedRunsResponse(BaseModel):
    items: list[TaskRunOut]
    total: int
    offset: int
    limit: int


class TaskLogOut(BaseModel):
    id: int
    run_id: int
    timestamp: datetime
    level: str
    phase: str | None
    message: str
    metadata_: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class RejectRequest(BaseModel):
    reason: str = ""


class PickWinnerRequest(BaseModel):
    winner: str  # "a" or "b"


class AdvancePhaseRequest(BaseModel):
    force: bool = False


class TerminalActionRequest(BaseModel):
    action: str  # "continue" | "pause" | "complete"


class PlanReviewRequest(BaseModel):
    action: str  # "approve" | "reject"
    modified_subtasks: list[dict] | None = None
    rejection_reason: str | None = None


class CreateRunRequest(BaseModel):
    project_id: str
    title: str
    description: str = ""
    workflow_template_id: int | None = None
    labels: list[str] = []
    run_type: str = "ai_task"
    agent_override: str | None = None
    workspace_server_id: int | None = None
    phase_overrides: dict[str, dict] | None = None
    issue_number: int | None = None
    issue_url: str | None = None
    skip_schedule: bool = False


class CreateRunResponse(BaseModel):
    id: int
    status: str
    title: str
    project_id: str
    branch_name: str

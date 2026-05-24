# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator


class ThresholdRule(BaseModel):
    metric: str  # test_coverage, lint_errors
    operator: Literal["<", ">", "==", "<=", ">="]
    value: float
    task: str  # task description template, may use {metric}, {value}


class AutonomyConfig(BaseModel):
    execution_mode: Literal["structured", "autonomous", "hybrid", "multi_agent"] = "structured"
    plan_approval: Literal["none", "show_and_continue", "require_approval", "adaptive"] = "none"
    adaptive_max_files: int = 5
    merge_mode: Literal["pr_only", "auto_merge", "risk_based"] = "pr_only"
    auto_merge_max_files: int = 3
    auto_merge_require_green_ci: bool = True
    allow_agent_followups: bool = False
    max_followup_depth: int = 2
    threshold_rules: list[ThresholdRule] = []


class ProjectConfigCreate(BaseModel):
    project_id: str
    project_slug: str
    repo_owner: str
    repo_name: str
    default_branch: str = "main"
    task_source: str = "plane"
    git_provider: str = "gitea"
    workspace_config: dict[str, Any] | None = None
    ai_config: dict[str, Any] | None = None
    workspace_server_ids: list[int] = []
    workspace_path: str | None = None
    local_path: str | None = None
    worker_user_override: str | None = None
    git_provider_token: str | None = None
    integration_config: dict[str, Any] | None = None
    poll_enabled: bool = False
    poll_interval_minutes: int = 5

    @field_validator("workspace_server_ids")
    @classmethod
    def deduplicate_workspace_servers(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        seen: set[int] = set()
        return [x for x in v if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]


class ProjectConfigUpdate(BaseModel):
    project_slug: str | None = None
    repo_owner: str | None = None
    repo_name: str | None = None
    default_branch: str | None = None
    task_source: str | None = None
    git_provider: str | None = None
    workspace_config: dict[str, Any] | None = None
    ai_config: dict[str, Any] | None = None
    workspace_server_ids: list[int] | None = None
    workspace_path: str | None = None
    local_path: str | None = None
    worker_user_override: str | None = None
    git_provider_token: str | None = None
    autonomy_config: AutonomyConfig | None = None
    integration_config: dict[str, Any] | None = None
    poll_enabled: bool | None = None
    poll_interval_minutes: int | None = None

    @field_validator("workspace_server_ids")
    @classmethod
    def deduplicate_workspace_servers(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        seen: set[int] = set()
        return [x for x in v if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]


class ProjectConfigOut(BaseModel):
    project_id: str
    project_slug: str
    repo_owner: str
    repo_name: str
    default_branch: str
    task_source: str
    git_provider: str
    workspace_config: dict[str, Any] | None
    ai_config: dict[str, Any] | None
    workspace_server_ids: list[int] = []
    workspace_path: str | None = None
    local_path: str | None = None
    worker_user_override: str | None = None
    has_git_provider_token: bool = False
    autonomy_config: dict[str, Any] | None = None
    integration_config: dict[str, Any] = {}
    poll_enabled: bool = False
    poll_interval_minutes: int = 5
    last_polled_at: datetime | None = None
    next_poll_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GitUrlParseRequest(BaseModel):
    git_url: str
    workspace_server_id: int | None = None


class GitUrlParseResponse(BaseModel):
    provider: str
    owner: str
    repo: str
    host: str
    default_branch: str
    suggested_slug: str
    suggested_id: str
    provider_confirmed: bool  # False if provider was "unknown"


class TestConnectionRequest(BaseModel):
    workspace_server_id: int
    git_url: str


class TestConnectionResponse(BaseModel):
    success: bool
    error: str | None = None


class WorkspaceReadinessItem(BaseModel):
    server_id: int
    server_name: str
    status: str  # "ready", "not_cloned", "error", "unreachable"
    path: str | None = None
    error: str | None = None


class WorkspaceReadinessResponse(BaseModel):
    project_id: str
    workspaces: list[WorkspaceReadinessItem]


class GitIssueOut(BaseModel):
    number: int
    title: str
    body: str
    labels: list[str] = []
    url: str
    state: str = "open"

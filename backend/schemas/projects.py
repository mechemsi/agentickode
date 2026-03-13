# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime
from typing import Any

from pydantic import BaseModel


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
    workspace_server_id: int | None = None
    workspace_path: str | None = None
    git_provider_token: str | None = None


class ProjectConfigUpdate(BaseModel):
    project_slug: str | None = None
    repo_owner: str | None = None
    repo_name: str | None = None
    default_branch: str | None = None
    task_source: str | None = None
    git_provider: str | None = None
    workspace_config: dict[str, Any] | None = None
    ai_config: dict[str, Any] | None = None
    workspace_server_id: int | None = None
    workspace_path: str | None = None
    git_provider_token: str | None = None


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
    workspace_server_id: int | None = None
    workspace_path: str | None = None
    has_git_provider_token: bool = False
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


class GitIssueOut(BaseModel):
    number: int
    title: str
    body: str
    labels: list[str] = []
    url: str
    state: str = "open"

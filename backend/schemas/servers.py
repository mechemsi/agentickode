# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class WorkspaceServerCreate(BaseModel):
    name: str
    hostname: str
    port: int = 22
    username: str = "root"
    ssh_key_path: str | None = None
    worker_user: str | None = "coder"
    workspace_root: str | None = None  # if set, use this instead of auto-creating
    setup_password: str | None = None  # transient — used to deploy SSH key, never stored


class WorkspaceServerUpdate(BaseModel):
    name: str | None = None
    hostname: str | None = None
    port: int | None = None
    username: str | None = None
    ssh_key_path: str | None = None
    worker_user: str | None = None
    workspace_root: str | None = None


class DiscoveredAgentOut(BaseModel):
    id: int
    agent_name: str
    agent_type: str
    path: str | None
    version: str | None
    available: bool
    metadata_: dict[str, Any] | None = None
    discovered_at: datetime

    model_config = {"from_attributes": True}


class SSHTestResult(BaseModel):
    success: bool
    latency_ms: float | None = None
    error: str | None = None


class ScanResult(BaseModel):
    agents_found: int
    projects_found: int
    projects_imported: int


class RetrySetupRequest(BaseModel):
    setup_password: str | None = None


class DeployKeyRequest(BaseModel):
    password: str


class WorkerUserPasswordRequest(BaseModel):
    password: str


class WorkerUserPasswordResult(BaseModel):
    success: bool
    error: str | None = None


class WorkerUserSetupRequest(BaseModel):
    username: str = "coder"


class WorkerUserSetupResult(BaseModel):
    success: bool
    username: str
    status: str  # "ready" | "error"
    agents: list[str] = []
    error: str | None = None


class WorkerUserStatus(BaseModel):
    username: str | None
    status: str | None  # null | "pending" | "ready" | "error"
    error: str | None = None
    agents: list[str] = []


class WorkspaceServerOut(BaseModel):
    id: int
    name: str
    hostname: str
    port: int
    username: str
    ssh_key_path: str | None
    workspace_root: str
    status: str
    last_seen_at: datetime | None
    error_message: str | None
    worker_user: str | None = None
    worker_user_status: str | None = None
    worker_user_password: str | None = None
    setup_log: dict[str, Any] | None = None
    agent_count: int = 0
    project_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceServerDetail(WorkspaceServerOut):
    agents: list[DiscoveredAgentOut] = []
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AgentSettingsIn(BaseModel):
    display_name: str | None = None
    description: str | None = None
    supports_session: bool | None = None
    default_timeout: int | None = None
    max_retries: int | None = None
    environment_vars: dict | None = None
    cli_flags: dict | None = None
    command_templates: dict | None = None
    enabled: bool | None = None
    agent_type: str | None = None
    install_cmd: str | None = None
    post_install_cmd: str | None = None
    check_cmd: str | None = None
    prereq_check: str | None = None
    prereq_name: str | None = None
    needs_non_root: bool | None = None
    consolidated_default: bool | None = None
    agent_creates_pr: bool | None = None


class AgentSettingsOut(BaseModel):
    id: int
    agent_name: str
    display_name: str
    description: str
    supports_session: bool
    default_timeout: int
    max_retries: int
    environment_vars: dict
    cli_flags: dict
    command_templates: dict
    enabled: bool
    agent_type: str = "cli_binary"
    install_cmd: str | None = None
    post_install_cmd: str | None = None
    check_cmd: str | None = None
    prereq_check: str | None = None
    prereq_name: str | None = None
    needs_non_root: bool = False
    consolidated_default: bool = True
    agent_creates_pr: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentInstallStatus(BaseModel):
    agent_name: str
    display_name: str
    description: str
    agent_type: str  # cli_binary | api_service
    installed: bool
    version: str | None = None
    path: str | None = None
    authenticated: bool | None = None
    auth_email: str | None = None
    auth_method: str | None = None


class AgentInstallRequest(BaseModel):
    agent_name: str


class AgentInstallResult(BaseModel):
    success: bool
    agent_name: str
    message: str | None = None
    error: str | None = None
    output: str | None = None


class UserAgentStatus(BaseModel):
    user: str
    agents: list[AgentInstallStatus]


class AgentManagementStatus(BaseModel):
    agents: list[AgentInstallStatus]
    by_user: list[UserAgentStatus] = []


class AgentInvocationOut(BaseModel):
    id: int
    run_id: int
    phase_execution_id: int | None = None
    workspace_server_id: int | None = None
    agent_name: str
    phase_name: str | None = None
    subtask_index: int | None = None
    subtask_title: str | None = None
    prompt_chars: int = 0
    response_chars: int = 0
    exit_code: int | None = None
    files_changed: list[str] | None = None
    duration_seconds: float | None = None
    estimated_tokens_in: int | None = None
    estimated_tokens_out: int | None = None
    estimated_cost_usd: float | None = None
    status: str = "running"
    error_message: str | None = None
    session_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata_: dict[str, Any] | None = None
    # Don't include full prompt/response text in list views — too large

    model_config = ConfigDict(from_attributes=True)


class AgentInvocationDetail(AgentInvocationOut):
    """Includes full prompt and response text for detail view."""

    prompt_text: str | None = None
    response_text: str | None = None
    system_prompt_text: str | None = None

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pydantic schemas for CLI session endpoints."""

from datetime import datetime

from pydantic import BaseModel


class CliSessionCreate(BaseModel):
    workspace_server_id: int
    agent_name: str
    user_context: str = "coder"
    project_id: str | None = None
    workspace_path: str | None = None
    display_name: str | None = None


class CliSessionOut(BaseModel):
    id: int
    session_id: str
    workspace_server_id: int
    server_name: str | None = None
    project_id: str | None = None
    task_run_id: int | None = None
    agent_name: str
    user_context: str
    workspace_path: str | None = None
    display_name: str | None = None
    tmux_session: str
    status: str
    remote_control_enabled: bool
    started_at: datetime
    last_activity_at: datetime
    closed_at: datetime | None = None
    model_config = {"from_attributes": True}


class SessionSendRequest(BaseModel):
    message: str


class SessionSendResponse(BaseModel):
    success: bool
    output: str | None = None


class SessionCaptureResponse(BaseModel):
    output: str
    lines: int

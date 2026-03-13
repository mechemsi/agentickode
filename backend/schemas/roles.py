# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime

from pydantic import BaseModel

DEFAULT_VALID_ROLES = {"planner", "coder", "reviewer", "fast"}
VALID_ROLES = DEFAULT_VALID_ROLES
VALID_PROVIDER_TYPES = {"ollama", "agent"}
VALID_AGENT_NAMES = {"claude", "codex", "opencode", "aider", "openhands"}


class RoleAssignmentCreate(BaseModel):
    role: str  # planner / coder / reviewer / fast
    provider_type: str  # ollama / agent
    ollama_server_id: int | None = None
    model_name: str | None = None
    agent_name: str | None = None
    workspace_server_id: int | None = None  # null = global default
    priority: int = 0  # 0 = primary, 1 = fallback


class RoleAssignmentOut(BaseModel):
    id: int
    role: str
    provider_type: str
    ollama_server_id: int | None
    model_name: str | None
    agent_name: str | None
    workspace_server_id: int | None
    workspace_server_name: str | None = None
    ollama_server_name: str | None = None
    priority: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

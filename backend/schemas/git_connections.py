# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pydantic schemas for git connections."""

from datetime import datetime

from pydantic import BaseModel

VALID_GIT_PROVIDERS = {"github", "gitea", "gitlab", "bitbucket"}
VALID_SCOPES = {"global", "server", "project"}


class GitConnectionCreate(BaseModel):
    name: str
    provider: str
    base_url: str | None = None
    token: str  # plaintext, encrypted before storage
    scope: str = "global"
    workspace_server_id: int | None = None
    project_id: str | None = None
    is_default: bool = False


class GitConnectionUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    token: str | None = None  # only updates if provided
    is_default: bool | None = None


class GitConnectionOut(BaseModel):
    id: int
    name: str
    provider: str
    base_url: str | None
    scope: str
    workspace_server_id: int | None
    project_id: str | None
    is_default: bool
    has_token: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GitConnectionTestResult(BaseModel):
    success: bool
    username: str | None = None
    error: str | None = None

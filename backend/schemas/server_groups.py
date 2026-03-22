# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime

from pydantic import BaseModel


class ServerGroupCreate(BaseModel):
    name: str
    description: str | None = None


class ServerGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ServerGroupSetToken(BaseModel):
    git_token: str
    git_provider_type: str  # "github", "gitea", "gitlab", "bitbucket"


class ServerGroupServerInfo(BaseModel):
    id: int
    name: str
    hostname: str
    status: str

    model_config = {"from_attributes": True}


class ServerGroupOut(BaseModel):
    id: int
    name: str
    description: str | None
    git_provider_type: str | None
    has_git_token: bool = False
    server_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServerGroupDetail(ServerGroupOut):
    servers: list[ServerGroupServerInfo] = []

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class OllamaServerCreate(BaseModel):
    name: str
    url: str


class OllamaServerUpdate(BaseModel):
    name: str | None = None
    url: str | None = None


class OllamaServerOut(BaseModel):
    id: int
    name: str
    url: str
    status: str
    last_seen_at: datetime | None
    error_message: str | None
    cached_models: list[dict[str, Any]] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunningModel(BaseModel):
    name: str
    model: str | None = None
    size: int = 0
    size_vram: int = 0
    digest: str | None = None
    expires_at: str | None = None
    details: dict[str, Any] | None = None


class RunningModelsResponse(BaseModel):
    server_id: int
    server_name: str
    server_url: str
    status: str
    models: list[RunningModel] = []
    error: str | None = None


class GpuStatusResponse(BaseModel):
    servers: list[RunningModelsResponse]


class PreloadRequest(BaseModel):
    model: str
    keep_alive: str | int = -1


class UnloadRequest(BaseModel):
    model: str


class PreloadResult(BaseModel):
    success: bool
    model: str
    error: str | None = None
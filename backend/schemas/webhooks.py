# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime

from pydantic import BaseModel


class WebhookCallbackCreate(BaseModel):
    url: str
    events: list[str] = []
    headers: dict[str, str] = {}
    active: bool = True


class WebhookCallbackUpdate(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    headers: dict[str, str] | None = None
    active: bool | None = None


class WebhookCallbackOut(BaseModel):
    id: int
    run_id: int
    url: str
    events: list[str]
    headers: dict[str, str]
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
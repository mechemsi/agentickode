# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime
from typing import Any

from pydantic import BaseModel

VALID_CHANNEL_TYPES = {"telegram", "slack", "discord", "webhook"}
VALID_NOTIFICATION_EVENTS = {
    "run_started",
    "run_completed",
    "run_failed",
    "approval_requested",
    "phase_completed",
    "phase_failed",
    "phase_waiting",
    "plan_review_requested",
    "cost_threshold_exceeded",
}


class NotificationChannelCreate(BaseModel):
    name: str
    channel_type: str
    config: dict[str, Any] = {}
    events: list[str] = []
    enabled: bool = True


class NotificationChannelUpdate(BaseModel):
    name: str | None = None
    channel_type: str | None = None
    config: dict[str, Any] | None = None
    events: list[str] | None = None
    enabled: bool | None = None


class NotificationChannelOut(BaseModel):
    id: int
    name: str
    channel_type: str
    config: dict[str, Any]
    events: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationTestResult(BaseModel):
    success: bool
    error: str | None = None
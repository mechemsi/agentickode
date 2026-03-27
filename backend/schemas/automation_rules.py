# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pydantic schemas for automation rule CRUD."""

from datetime import datetime

from pydantic import BaseModel

VALID_EVENT_SOURCES = {"run_event", "webhook", "monitoring", "schedule", "notification"}
VALID_ACTION_TYPES = {"create_run", "notify", "send_message", "update_issue"}


class AutomationRuleCreate(BaseModel):
    name: str
    description: str | None = None
    event_source: str  # run_event, webhook, monitoring, schedule
    event_filter: dict = {}
    action_type: str  # create_run, notify, send_message, update_issue
    action_config: dict = {}
    cooldown_seconds: int = 300
    enabled: bool = True


class AutomationRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    event_source: str | None = None
    event_filter: dict | None = None
    action_type: str | None = None
    action_config: dict | None = None
    cooldown_seconds: int | None = None
    enabled: bool | None = None


class AutomationRuleOut(BaseModel):
    id: int
    project_id: str | None
    name: str
    description: str | None
    event_source: str
    event_filter: dict
    action_type: str
    action_config: dict
    cooldown_seconds: int
    last_triggered_at: datetime | None
    trigger_count: int
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}

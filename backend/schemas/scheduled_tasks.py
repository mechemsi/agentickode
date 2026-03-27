# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pydantic schemas for scheduled task CRUD."""

from datetime import datetime

from pydantic import BaseModel, field_validator

from backend.services.cron_parser import validate_cron


class ScheduledTaskCreate(BaseModel):
    name: str
    schedule: str  # cron expression, e.g. "0 3 * * *"
    task_description: str
    enabled: bool = True

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, v: str) -> str:
        if not validate_cron(v):
            raise ValueError(f"Invalid cron expression: {v}")
        return v


class ScheduledTaskUpdate(BaseModel):
    name: str | None = None
    schedule: str | None = None
    task_description: str | None = None
    enabled: bool | None = None

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, v: str | None) -> str | None:
        if v is not None and not validate_cron(v):
            raise ValueError(f"Invalid cron expression: {v}")
        return v


class ScheduledTaskOut(BaseModel):
    id: int
    project_id: str
    name: str
    schedule: str
    task_description: str
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}

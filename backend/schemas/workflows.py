# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LabelRule(BaseModel):
    match_all: list[str] = []
    match_any: list[str] = []


class PhaseConfig(BaseModel):
    phase_name: str
    enabled: bool = True
    role: str | None = None
    uses_agent: bool | None = None
    agent_mode: str | None = None
    timeout_seconds: int | None = None
    trigger_mode: str = "auto"
    notify_source: bool = False
    params: dict[str, Any] = {}
    cli_flags: dict[str, str] | None = None
    environment_vars: dict[str, str] | None = None
    command_templates: dict[str, str] | None = None


class WorkflowTemplateCreate(BaseModel):
    name: str
    description: str = ""
    label_rules: list[LabelRule] = []
    phases: list[PhaseConfig] = []
    is_default: bool = False
    is_system: bool = False


class WorkflowTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    label_rules: list[LabelRule] | None = None
    phases: list[PhaseConfig] | None = None


class WorkflowTemplateOut(BaseModel):
    id: int
    name: str
    description: str
    label_rules: list[dict[str, Any]]
    phases: list[dict[str, Any]]
    is_default: bool
    is_system: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
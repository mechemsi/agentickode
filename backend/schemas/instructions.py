# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pydantic schemas for project instructions and secrets."""

from datetime import datetime

from pydantic import BaseModel


class ProjectInstructionIn(BaseModel):
    content: str
    is_active: bool = True


class ProjectInstructionOut(BaseModel):
    id: int
    project_id: str
    phase_name: str
    content: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectSecretIn(BaseModel):
    name: str
    value: str
    inject_as: str = "env_var"
    phase_scope: str | None = None


class ProjectSecretOut(BaseModel):
    id: int
    project_id: str
    name: str
    inject_as: str
    phase_scope: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectSecretUpdate(BaseModel):
    value: str | None = None
    inject_as: str | None = None
    phase_scope: str | None = None


class InstructionVersionOut(BaseModel):
    id: int
    instruction_id: int
    content: str
    changed_at: datetime
    change_summary: str | None

    model_config = {"from_attributes": True}


class PromptPreviewRequest(BaseModel):
    phase_name: str


class PromptPreviewResponse(BaseModel):
    system_prompt_section: str
    secrets_injected: list[str]
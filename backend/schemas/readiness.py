# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pydantic schemas for workspace readiness validation."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, computed_field


class CheckResultOut(BaseModel):
    name: str
    category: str
    status: str
    command: str
    output: str
    duration_s: float
    fix_suggestion: str | None = None

    model_config = {"from_attributes": True}


class WorkspaceReadinessOut(BaseModel):
    id: int
    project_id: str
    workspace_server_id: int
    validation_status: str
    validated_at: datetime | None = None
    expires_at: datetime | None = None
    check_results: list[dict[str, Any]] | None = None
    validation_report: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_expired(self) -> bool:
        if self.validation_status != "passed":
            return True
        if self.expires_at is None:
            return True
        return self.expires_at < datetime.now(UTC)

    model_config = {"from_attributes": True}

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Pydantic schemas for monitoring rules."""

from datetime import datetime

from pydantic import BaseModel

VALID_SOURCES = {"sentry", "datadog", "grafana", "pagerduty", "generic"}
VALID_SEVERITIES = {"debug", "info", "warning", "error", "critical", "fatal"}


class MonitoringRuleCreate(BaseModel):
    source: str  # sentry, datadog, grafana, pagerduty, generic
    min_severity: str = "error"
    task_template: str  # description template for created runs
    enabled: bool = True


class MonitoringRuleUpdate(BaseModel):
    source: str | None = None
    min_severity: str | None = None
    task_template: str | None = None
    enabled: bool | None = None


class MonitoringRuleOut(BaseModel):
    id: int
    project_id: str
    source: str
    min_severity: str
    task_template: str
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}

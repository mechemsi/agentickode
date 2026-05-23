# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class LabelRule(BaseModel):
    match_all: list[str] = []
    match_any: list[str] = []


# Trigger source — which integration emitted the event. ``any`` means the
# rule fires regardless of source (back-compat with label-based routing).
TriggerSource = Literal["github", "gitea", "gitlab", "plane", "notion", "any"]


class LabelTrigger(BaseModel):
    """Match incoming events by their label/tag set.

    Equivalent of the legacy ``label_rules`` mechanism but with a source filter.
    Used for label-only events (e.g. Notion tags) and as a fallback for
    issue/PR events that also carry labels.
    """

    type: Literal["label"] = "label"
    source: TriggerSource = "any"
    match_all: list[str] = []
    match_any: list[str] = []


class IssueEventTrigger(BaseModel):
    """Match issue-shaped events (GitHub/Gitea/GitLab/Plane/Notion issues)."""

    type: Literal["issue_event"] = "issue_event"
    source: TriggerSource = "any"
    action: Literal["opened", "labeled", "commented", "any"] = "any"
    label_filter: list[str] = []  # ANDed with action match when non-empty


class PrEventTrigger(BaseModel):
    """Match pull/merge-request events."""

    type: Literal["pr_event"] = "pr_event"
    source: Literal["github", "gitea", "gitlab", "any"] = "any"
    action: Literal["opened", "review_requested", "labeled", "comment", "any"] = "any"
    label_filter: list[str] = []


class ScheduleTrigger(BaseModel):
    """Fire on a cron schedule. ``cron`` is a standard 5-field expression."""

    type: Literal["schedule"] = "schedule"
    cron: str


class ManualTrigger(BaseModel):
    """Sentinel trigger — never matches an external event.

    Used to mark templates that should only be dispatched via direct API hits
    (``POST /api/runs`` with an explicit ``workflow_template_id``).
    """

    type: Literal["manual"] = "manual"


WorkflowTriggerRule = Annotated[
    LabelTrigger | IssueEventTrigger | PrEventTrigger | ScheduleTrigger | ManualTrigger,
    Field(discriminator="type"),
]


class PhaseConfig(BaseModel):
    phase_name: str
    kind: Literal["legacy_phase", "bash", "agent"] = "legacy_phase"
    enabled: bool = True
    role: str | None = None
    uses_agent: bool | None = None
    agent_mode: str | None = None
    timeout_seconds: int | None = None
    trigger_mode: str = "auto"
    failure_mode: Literal["fail", "skip"] = "fail"
    notify_source: bool = False
    params: dict[str, Any] = {}
    cli_flags: dict[str, str] | None = None
    environment_vars: dict[str, str] | None = None
    command_templates: dict[str, str] | None = None


class WorkflowTemplateCreate(BaseModel):
    name: str
    description: str = ""
    label_rules: list[LabelRule] = []
    triggers: list[WorkflowTriggerRule] = []
    phases: list[PhaseConfig] = []
    is_default: bool = False
    is_system: bool = False


class WorkflowTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    label_rules: list[LabelRule] | None = None
    triggers: list[WorkflowTriggerRule] | None = None
    phases: list[PhaseConfig] | None = None


class WorkflowTemplateOut(BaseModel):
    id: int
    name: str
    description: str
    label_rules: list[dict[str, Any]]
    triggers: list[dict[str, Any]] = []
    phases: list[dict[str, Any]]
    is_default: bool
    is_system: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

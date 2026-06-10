# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from typing import Annotated, Literal

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
    """Fire on a cron schedule. ``cron`` is a standard 5-field expression.

    ``project_id`` is required for the scheduler to actually create a TaskRun
    (schedule triggers without a project context are skipped at dispatch).
    Modelled as optional in the schema so a template can carry a schedule
    trigger that's only valid once a project is assigned, but the
    ScheduleTriggerScheduler will no-op until ``project_id`` is set.
    """

    type: Literal["schedule"] = "schedule"
    cron: str
    project_id: str | None = None


class ManualTrigger(BaseModel):
    """Sentinel trigger — never matches an external event.

    Marks a flow prompt that should only be dispatched via direct API hits
    (``POST /api/runs`` with an explicit ``flow_prompt_id``).
    """

    type: Literal["manual"] = "manual"


WorkflowTriggerRule = Annotated[
    LabelTrigger | IssueEventTrigger | PrEventTrigger | ScheduleTrigger | ManualTrigger,
    Field(discriminator="type"),
]

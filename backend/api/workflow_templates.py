# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workflow template CRUD + label matching endpoint."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import WorkflowTemplate
from backend.repositories.workflow_template_repo import WorkflowTemplateRepository
from backend.schemas import (
    WorkflowTemplateCreate,
    WorkflowTemplateOut,
    WorkflowTemplateUpdate,
)
from backend.services.triggers import TriggerEvent, TriggerMatcher
from backend.worker.phases.registry import discover_phases

router = APIRouter(tags=["workflow-templates"])


class MatchLabelsRequest(BaseModel):
    labels: list[str]


class DryRunRequest(BaseModel):
    """Payload for ``POST /workflow-templates/{id}/dry-run``.

    Mirrors the ``TriggerEvent`` dataclass so the UI can ask "would this
    template fire for this event?" without inventing a separate vocabulary.
    """

    type: Literal["label", "issue_event", "pr_event", "schedule"]
    source: str = "any"
    labels: list[str] = []
    action: str | None = None
    cron_tick: str | None = None


class DryRunResponse(BaseModel):
    matched: bool
    template: WorkflowTemplateOut | None
    reason: str


def _get_repo(db: AsyncSession = Depends(get_db)) -> WorkflowTemplateRepository:
    return WorkflowTemplateRepository(db)


@router.get("/phases")
async def list_phases():
    """Return all discovered pipeline phases with their metadata."""
    return [
        {
            "name": info.name,
            "description": info.description,
            "default_role": info.default_role,
            "default_agent_mode": info.default_agent_mode,
            "kind": info.kind,
            "deprecated_in": info.deprecated_in,
        }
        for info in sorted(discover_phases().values(), key=lambda i: i.name)
    ]


@router.get("/step-kinds")
async def list_step_kinds():
    """Return the composable step kinds the workflow builder can use.

    The frontend builder renders kind-specific param editors based on this.
    ``legacy_phase`` enumerates the discovered phase modules; ``bash`` and
    ``agent`` are the generic primitives introduced by ADR-007.
    """
    return [
        {
            "kind": "bash",
            "description": "Run a shell command on the workspace server.",
            "params_schema": {
                "command": {
                    "type": "string",
                    "required": True,
                    "description": (
                        "Shell command. Supports {{run.title}}, {{run.description}}, "
                        "{{run.task_id}}, and {{steps.NAME.field}} substitution."
                    ),
                }
            },
        },
        {
            "kind": "agent",
            "description": "Invoke a configured agent (via RoleResolver).",
            "params_schema": {
                "prompt": {
                    "type": "string",
                    "required": True,
                    "description": "Instruction sent to the agent (templating supported).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["generate", "task"],
                    "default": "generate",
                    "description": "generate -> adapter.generate; task -> adapter.run_task with workspace.",
                },
                "session_id": {
                    "type": "string",
                    "required": False,
                    "description": "Optional CLI session id (e.g. Claude --resume).",
                },
                "new_session": {
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
        },
        {
            "kind": "legacy_phase",
            "description": (
                "Run a built-in phase module by name. Discovered modules are listed "
                "in `values` and via GET /phases. Defaults when `kind` is omitted."
            ),
            "values": sorted(discover_phases().keys()),
        },
    ]


@router.get("/workflow-templates", response_model=list[WorkflowTemplateOut])
async def list_workflow_templates(
    repo: WorkflowTemplateRepository = Depends(_get_repo),
):
    return await repo.list_all()


@router.get("/workflow-templates/{template_id}", response_model=WorkflowTemplateOut)
async def get_workflow_template(
    template_id: int,
    repo: WorkflowTemplateRepository = Depends(_get_repo),
):
    template = await repo.get_by_id(template_id)
    if not template:
        raise HTTPException(404, "Workflow template not found")
    return template


@router.post("/workflow-templates", response_model=WorkflowTemplateOut, status_code=201)
async def create_workflow_template(
    body: WorkflowTemplateCreate,
    repo: WorkflowTemplateRepository = Depends(_get_repo),
):
    template = WorkflowTemplate(
        name=body.name,
        description=body.description,
        label_rules=[r.model_dump() for r in body.label_rules],
        triggers=[t.model_dump() for t in body.triggers],
        phases=[p.model_dump() for p in body.phases],
        is_default=body.is_default,
    )
    return await repo.create(template)


@router.put("/workflow-templates/{template_id}", response_model=WorkflowTemplateOut)
async def update_workflow_template(
    template_id: int,
    body: WorkflowTemplateUpdate,
    repo: WorkflowTemplateRepository = Depends(_get_repo),
):
    template = await repo.get_by_id(template_id)
    if not template:
        raise HTTPException(404, "Workflow template not found")
    data = body.model_dump(exclude_unset=True)
    if "label_rules" in data:
        data["label_rules"] = [
            r.model_dump() if hasattr(r, "model_dump") else r for r in data["label_rules"]
        ]
    if "triggers" in data:
        data["triggers"] = [
            t.model_dump() if hasattr(t, "model_dump") else t for t in data["triggers"]
        ]
    if "phases" in data:
        data["phases"] = [p.model_dump() if hasattr(p, "model_dump") else p for p in data["phases"]]
    return await repo.update(template, data)


@router.delete("/workflow-templates/{template_id}", status_code=204)
async def delete_workflow_template(
    template_id: int,
    repo: WorkflowTemplateRepository = Depends(_get_repo),
):
    template = await repo.get_by_id(template_id)
    if not template:
        raise HTTPException(404, "Workflow template not found")
    if template.is_default:
        raise HTTPException(400, "Cannot delete the default workflow template")
    if template.is_system:
        raise HTTPException(400, "Cannot delete a system workflow template")
    await repo.delete(template)


@router.post("/workflow-templates/match", response_model=WorkflowTemplateOut)
async def match_workflow_template(
    body: MatchLabelsRequest,
    repo: WorkflowTemplateRepository = Depends(_get_repo),
):
    template = await repo.match_labels(body.labels)
    if not template:
        raise HTTPException(404, "No matching workflow template found")
    return template


@router.post("/workflow-templates/{template_id}/dry-run", response_model=DryRunResponse)
async def dry_run_template(
    template_id: int,
    body: DryRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Test whether a given event would fire this template's triggers.

    Returns ``matched=True`` and a human-readable ``reason`` like
    ``"matched trigger #2 (LabelTrigger source=github)"`` when any of the
    template's ``triggers[]`` entries match the synthetic event, otherwise
    ``matched=False`` with ``"no triggers matched"``.

    This is for the UI's trigger preview — when the user edits triggers they
    want to confirm "would this fire for X event?".
    """
    repo = WorkflowTemplateRepository(db)
    template = await repo.get_by_id(template_id)
    if not template:
        raise HTTPException(404, "Workflow template not found")

    event = TriggerEvent(
        type=body.type,
        source=body.source,
        labels=body.labels,
        action=body.action,
        cron_tick=body.cron_tick,
    )

    triggers = template.triggers or []
    for idx, trigger in enumerate(triggers):
        if TriggerMatcher._trigger_matches(trigger, event):
            ttype = trigger.get("type", "unknown")
            tsource = trigger.get("source", "any")
            reason = f"matched trigger #{idx} ({ttype} source={tsource})"
            return DryRunResponse(matched=True, template=template, reason=reason)

    return DryRunResponse(matched=False, template=None, reason="no triggers matched")

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workflow template CRUD + label matching endpoint."""

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
from backend.worker.phases.registry import discover_phases

router = APIRouter(tags=["workflow-templates"])


class MatchLabelsRequest(BaseModel):
    labels: list[str]


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
        }
        for info in sorted(discover_phases().values(), key=lambda i: i.name)
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
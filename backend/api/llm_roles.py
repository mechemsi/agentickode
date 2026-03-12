# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Role assignment management — unified provider configuration."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import OllamaServer, RoleAssignment, WorkspaceServer
from backend.repositories.role_assignment_repo import RoleAssignmentRepository
from backend.repositories.role_config_repo import RoleConfigRepository
from backend.schemas import (
    DEFAULT_VALID_ROLES,
    VALID_AGENT_NAMES,
    VALID_PROVIDER_TYPES,
    RoleAssignmentCreate,
    RoleAssignmentOut,
)

router = APIRouter(tags=["role-assignments"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> RoleAssignmentRepository:
    return RoleAssignmentRepository(db)


def _to_out(ra: RoleAssignment) -> RoleAssignmentOut:
    """Convert model to output schema with denormalized names."""
    return RoleAssignmentOut(
        id=ra.id,
        role=ra.role,
        provider_type=ra.provider_type,
        ollama_server_id=ra.ollama_server_id,
        model_name=ra.model_name,
        agent_name=ra.agent_name,
        workspace_server_id=ra.workspace_server_id,
        workspace_server_name=ra.workspace_server.name if ra.workspace_server else None,
        ollama_server_name=ra.ollama_server.name if ra.ollama_server else None,
        priority=ra.priority,
        created_at=ra.created_at,
        updated_at=ra.updated_at,
    )


@router.get("/role-assignments", response_model=list[RoleAssignmentOut])
async def list_role_assignments(
    scope_server_id: int | None = Query(None),
    repo: RoleAssignmentRepository = Depends(_get_repo),
):
    roles = await repo.list_all(workspace_server_id=scope_server_id)
    return [_to_out(r) for r in roles]


@router.put("/role-assignments", response_model=list[RoleAssignmentOut])
async def bulk_upsert_role_assignments(
    body: list[RoleAssignmentCreate],
    db: AsyncSession = Depends(get_db),
):
    repo = RoleAssignmentRepository(db)

    for item in body:
        await _validate_assignment(item, db)
        await _validate_references(item, db)

    results = await repo.bulk_upsert([item.model_dump() for item in body])

    # Reload with relationships for denormalized output
    refreshed = await repo.list_all()
    id_map = {r.id: r for r in refreshed}
    return [_to_out(id_map[r.id]) for r in results if r.id in id_map]


@router.delete("/role-assignments/{assignment_id}", status_code=204)
async def delete_role_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
):
    repo = RoleAssignmentRepository(db)
    existing = await db.get(RoleAssignment, assignment_id)
    if not existing:
        raise HTTPException(404, f"Role assignment {assignment_id} not found")
    await repo.delete(assignment_id)


# Keep legacy endpoint for backward compatibility during frontend transition
@router.get("/llm-roles", response_model=list[RoleAssignmentOut])
async def list_llm_roles_compat(
    repo: RoleAssignmentRepository = Depends(_get_repo),
):
    roles = await repo.list_all()
    return [_to_out(r) for r in roles]


async def _validate_assignment(item: RoleAssignmentCreate, db: AsyncSession) -> None:
    role_repo = RoleConfigRepository(db)
    valid_roles = (await role_repo.get_valid_role_names()) | DEFAULT_VALID_ROLES
    if item.role not in valid_roles:
        raise HTTPException(400, f"Invalid role: {item.role}")
    if item.provider_type not in VALID_PROVIDER_TYPES:
        raise HTTPException(400, f"Invalid provider_type: {item.provider_type}")
    if item.priority not in (0, 1):
        raise HTTPException(400, "priority must be 0 (primary) or 1 (fallback)")
    if item.provider_type == "ollama":
        if not item.ollama_server_id or not item.model_name:
            raise HTTPException(400, "ollama provider requires ollama_server_id and model_name")
    elif item.provider_type == "agent":
        if not item.agent_name:
            raise HTTPException(400, "agent provider requires agent_name")
        if item.agent_name not in VALID_AGENT_NAMES:
            raise HTTPException(400, f"Unknown agent: {item.agent_name}")


async def _validate_references(item: RoleAssignmentCreate, db: AsyncSession) -> None:
    if item.ollama_server_id:
        server = await db.get(OllamaServer, item.ollama_server_id)
        if not server:
            raise HTTPException(400, f"Ollama server {item.ollama_server_id} not found")
    if item.workspace_server_id:
        ws = await db.get(WorkspaceServer, item.workspace_server_id)
        if not ws:
            raise HTTPException(400, f"Workspace server {item.workspace_server_id} not found")
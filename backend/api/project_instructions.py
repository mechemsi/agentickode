# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""API routes for project instructions and secrets."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.project_instruction_repo import ProjectInstructionRepository
from backend.repositories.project_secret_repo import ProjectSecretRepository
from backend.schemas.instructions import (
    InstructionVersionOut,
    ProjectInstructionIn,
    ProjectInstructionOut,
    ProjectSecretIn,
    ProjectSecretOut,
    ProjectSecretUpdate,
    PromptPreviewRequest,
    PromptPreviewResponse,
)

router = APIRouter(tags=["project-instructions"])


def _instr_repo(db: AsyncSession = Depends(get_db)) -> ProjectInstructionRepository:
    return ProjectInstructionRepository(db)


def _secret_repo(db: AsyncSession = Depends(get_db)) -> ProjectSecretRepository:
    return ProjectSecretRepository(db)


# --- Instructions ---


@router.get(
    "/projects/{project_id}/instructions",
    response_model=list[ProjectInstructionOut],
)
async def list_instructions(
    project_id: str, repo: ProjectInstructionRepository = Depends(_instr_repo)
):
    return await repo.get_for_project(project_id)


@router.put(
    "/projects/{project_id}/instructions",
    response_model=ProjectInstructionOut,
)
async def upsert_global_instruction(
    project_id: str,
    body: ProjectInstructionIn,
    repo: ProjectInstructionRepository = Depends(_instr_repo),
):
    return await repo.upsert(project_id, "__global__", body.content)


@router.put(
    "/projects/{project_id}/instructions/{phase}",
    response_model=ProjectInstructionOut,
)
async def upsert_phase_instruction(
    project_id: str,
    phase: str,
    body: ProjectInstructionIn,
    repo: ProjectInstructionRepository = Depends(_instr_repo),
):
    if phase not in ("planning", "coding", "reviewing"):
        raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")
    return await repo.upsert(project_id, phase, body.content)


@router.delete("/projects/{project_id}/instructions/{phase}", status_code=204)
async def delete_instruction(
    project_id: str,
    phase: str,
    repo: ProjectInstructionRepository = Depends(_instr_repo),
):
    instruction = await repo.get_for_phase(project_id, phase)
    if not instruction:
        raise HTTPException(status_code=404, detail="Instruction not found")
    await repo.delete(instruction)


# --- Versions ---


@router.get(
    "/projects/{project_id}/instructions/versions",
    response_model=list[InstructionVersionOut],
)
async def list_versions(project_id: str, repo: ProjectInstructionRepository = Depends(_instr_repo)):
    instructions = await repo.get_for_project(project_id)
    versions = []
    for instr in instructions:
        versions.extend(await repo.get_versions(instr.id))
    versions.sort(key=lambda v: v.changed_at, reverse=True)
    return versions


# --- Secrets ---


@router.get(
    "/projects/{project_id}/secrets",
    response_model=list[ProjectSecretOut],
)
async def list_secrets(project_id: str, repo: ProjectSecretRepository = Depends(_secret_repo)):
    return await repo.list_for_project(project_id)


@router.post(
    "/projects/{project_id}/secrets",
    response_model=ProjectSecretOut,
    status_code=201,
)
async def create_secret(
    project_id: str,
    body: ProjectSecretIn,
    repo: ProjectSecretRepository = Depends(_secret_repo),
):
    return await repo.create(
        project_id=project_id,
        name=body.name,
        value=body.value,
        inject_as=body.inject_as,
        phase_scope=body.phase_scope,
    )


@router.put(
    "/projects/{project_id}/secrets/{secret_id}",
    response_model=ProjectSecretOut,
)
async def update_secret(
    project_id: str,
    secret_id: int,
    body: ProjectSecretUpdate,
    repo: ProjectSecretRepository = Depends(_secret_repo),
):
    secret = await repo.get_by_id(secret_id)
    if not secret or secret.project_id != project_id:
        raise HTTPException(status_code=404, detail="Secret not found")
    data = body.model_dump(exclude_none=True)
    return await repo.update(secret, data)


@router.delete("/projects/{project_id}/secrets/{secret_id}", status_code=204)
async def delete_secret(
    project_id: str,
    secret_id: int,
    repo: ProjectSecretRepository = Depends(_secret_repo),
):
    secret = await repo.get_by_id(secret_id)
    if not secret or secret.project_id != project_id:
        raise HTTPException(status_code=404, detail="Secret not found")
    await repo.delete(secret)


# --- Preview ---


@router.post(
    "/projects/{project_id}/instructions/preview",
    response_model=PromptPreviewResponse,
)
async def preview_prompt(
    project_id: str,
    body: PromptPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    from backend.worker.phases._prompt_resolver import build_project_instructions_section

    section, secret_names = await build_project_instructions_section(
        db, project_id, body.phase_name
    )
    return PromptPreviewResponse(
        system_prompt_section=section,
        secrets_injected=secret_names,
    )

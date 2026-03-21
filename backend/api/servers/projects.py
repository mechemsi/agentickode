# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Project listing endpoints scoped to workspace servers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import ProjectConfig
from backend.repositories.project_config_repo import ProjectConfigRepository
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas import ProjectConfigOut

router = APIRouter(tags=["server-projects"])


def _get_server_repo(db: AsyncSession = Depends(get_db)) -> WorkspaceServerRepository:
    return WorkspaceServerRepository(db)


def _get_project_repo(db: AsyncSession = Depends(get_db)) -> ProjectConfigRepository:
    return ProjectConfigRepository(db)


def _project_out(project: ProjectConfig) -> ProjectConfigOut:
    """Serialize a ProjectConfig ORM object to its output schema."""
    out = ProjectConfigOut.model_validate(project)
    out.has_git_provider_token = bool(project.git_provider_token_enc)
    out.workspace_server_ids = [ws.workspace_server_id for ws in project.workspace_servers]
    return out


@router.get(
    "/workspace-servers/{server_id}/projects",
    response_model=list[ProjectConfigOut],
)
async def list_server_projects(
    server_id: int,
    server_repo: WorkspaceServerRepository = Depends(_get_server_repo),
    project_repo: ProjectConfigRepository = Depends(_get_project_repo),
):
    """List projects linked to a specific workspace server."""
    server = await server_repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")
    projects = await project_repo.list_by_server(server_id)
    return [_project_out(p) for p in projects]

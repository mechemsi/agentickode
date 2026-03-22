# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Docker management endpoints for workspace servers."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.repositories.workspace_server_repo import WorkspaceServerRepository
from backend.schemas.docker import (
    ContainerInspectResponse,
    ContainerLogsResponse,
    DockerComposeStack,
    DockerContainer,
    DockerImage,
    DockerNetwork,
    DockerOverview,
    DockerVolume,
    PruneRequest,
    PruneResult,
)
from backend.services.workspace.docker_service import DockerService
from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.docker_management")

router = APIRouter(tags=["docker-management"])


async def _get_docker_service(server_id: int, db: AsyncSession) -> DockerService:
    """Load server from DB and return a DockerService wired to it."""
    repo = WorkspaceServerRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    ssh = SSHService.for_server(server)
    return DockerService(ssh)


@router.get(
    "/workspace-servers/{server_id}/docker/overview",
    response_model=DockerOverview,
)
async def docker_overview(server_id: int, db: AsyncSession = Depends(get_db)):
    """Get all Docker resources on server."""
    svc = await _get_docker_service(server_id, db)
    try:
        containers = await svc.list_containers(all=True)
        images = await svc.list_images()
        volumes = await svc.list_volumes()
        networks = await svc.list_networks()
        stacks = await svc.list_compose_stacks()
        du = await svc.disk_usage()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DockerOverview(
        containers=_parse_containers(containers),
        images=_parse_images(images),
        volumes=_parse_volumes(volumes),
        networks=_parse_networks(networks),
        stacks=_parse_stacks(stacks),
        disk_usage=du,
    )


@router.get(
    "/workspace-servers/{server_id}/docker/containers",
    response_model=list[DockerContainer],
)
async def list_containers(
    server_id: int,
    all: bool = True,
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_docker_service(server_id, db)
    try:
        raw = await svc.list_containers(all=all)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _parse_containers(raw)


@router.get(
    "/workspace-servers/{server_id}/docker/images",
    response_model=list[DockerImage],
)
async def list_images(server_id: int, db: AsyncSession = Depends(get_db)):
    svc = await _get_docker_service(server_id, db)
    try:
        raw = await svc.list_images()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _parse_images(raw)


@router.get(
    "/workspace-servers/{server_id}/docker/volumes",
    response_model=list[DockerVolume],
)
async def list_volumes(server_id: int, db: AsyncSession = Depends(get_db)):
    svc = await _get_docker_service(server_id, db)
    try:
        raw = await svc.list_volumes()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _parse_volumes(raw)


@router.get(
    "/workspace-servers/{server_id}/docker/networks",
    response_model=list[DockerNetwork],
)
async def list_networks(server_id: int, db: AsyncSession = Depends(get_db)):
    svc = await _get_docker_service(server_id, db)
    try:
        raw = await svc.list_networks()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _parse_networks(raw)


@router.get(
    "/workspace-servers/{server_id}/docker/stacks",
    response_model=list[DockerComposeStack],
)
async def list_stacks(server_id: int, db: AsyncSession = Depends(get_db)):
    svc = await _get_docker_service(server_id, db)
    try:
        raw = await svc.list_compose_stacks()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _parse_stacks(raw)


@router.get(
    "/workspace-servers/{server_id}/docker/containers/{container_id}/logs",
    response_model=ContainerLogsResponse,
)
async def container_logs(
    server_id: int,
    container_id: str,
    tail: int = 100,
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_docker_service(server_id, db)
    try:
        logs = await svc.container_logs(container_id, tail=tail)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ContainerLogsResponse(logs=logs)


@router.get(
    "/workspace-servers/{server_id}/docker/containers/{container_id}/inspect",
    response_model=ContainerInspectResponse,
)
async def container_inspect(
    server_id: int,
    container_id: str,
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_docker_service(server_id, db)
    try:
        data = await svc.container_inspect(container_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ContainerInspectResponse(data=data)


@router.post(
    "/workspace-servers/{server_id}/docker/containers/{container_id}/start",
    response_model=PruneResult,
)
async def start_container(
    server_id: int,
    container_id: str,
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_docker_service(server_id, db)
    try:
        out = await svc.start_container(container_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PruneResult(output=out.strip())


@router.post(
    "/workspace-servers/{server_id}/docker/containers/{container_id}/stop",
    response_model=PruneResult,
)
async def stop_container(
    server_id: int,
    container_id: str,
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_docker_service(server_id, db)
    try:
        out = await svc.stop_container(container_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PruneResult(output=out.strip())


@router.post(
    "/workspace-servers/{server_id}/docker/containers/{container_id}/restart",
    response_model=PruneResult,
)
async def restart_container(
    server_id: int,
    container_id: str,
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_docker_service(server_id, db)
    try:
        out = await svc.restart_container(container_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PruneResult(output=out.strip())


@router.delete(
    "/workspace-servers/{server_id}/docker/containers/{container_id}",
    response_model=PruneResult,
)
async def remove_container(
    server_id: int,
    container_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_docker_service(server_id, db)
    try:
        out = await svc.remove_container(container_id, force=force)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PruneResult(output=out.strip())


@router.delete(
    "/workspace-servers/{server_id}/docker/images/{image_id:path}",
    response_model=PruneResult,
)
async def remove_image(
    server_id: int,
    image_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_docker_service(server_id, db)
    try:
        out = await svc.remove_image(image_id, force=force)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PruneResult(output=out.strip())


@router.post(
    "/workspace-servers/{server_id}/docker/prune",
    response_model=PruneResult,
)
async def prune(
    server_id: int,
    body: PruneRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = await _get_docker_service(server_id, db)
    try:
        if body.target == "containers":
            out = await svc.prune_containers()
        elif body.target == "images":
            out = await svc.prune_images(all=body.all)
        elif body.target == "volumes":
            out = await svc.prune_volumes()
        elif body.target == "networks":
            out = await svc.prune_networks()
        elif body.target == "system":
            out = await svc.prune_system(all=body.all, volumes=body.include_volumes)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prune target: {body.target}",
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PruneResult(output=out.strip())


@router.get(
    "/workspace-servers/{server_id}/docker/disk-usage",
)
async def disk_usage(server_id: int, db: AsyncSession = Depends(get_db)):
    svc = await _get_docker_service(server_id, db)
    try:
        out = await svc.disk_usage()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"output": out}


# ---------------------------------------------------------------------------
# Helpers to normalise docker JSON output into schema objects
# ---------------------------------------------------------------------------


def _parse_containers(raw: list[dict]) -> list[DockerContainer]:
    return [
        DockerContainer(
            id=c.get("ID", ""),
            names=c.get("Names", ""),
            image=c.get("Image", ""),
            status=c.get("Status", ""),
            state=c.get("State", ""),
            ports=c.get("Ports", ""),
            created_at=c.get("CreatedAt"),
            size=c.get("Size"),
        )
        for c in raw
    ]


def _parse_images(raw: list[dict]) -> list[DockerImage]:
    return [
        DockerImage(
            id=i.get("ID", ""),
            repository=i.get("Repository", ""),
            tag=i.get("Tag", ""),
            size=i.get("Size", ""),
            created_at=i.get("CreatedAt") or i.get("CreatedSince"),
        )
        for i in raw
    ]


def _parse_volumes(raw: list[dict]) -> list[DockerVolume]:
    return [
        DockerVolume(
            name=v.get("Name", ""),
            driver=v.get("Driver", ""),
            mountpoint=v.get("Mountpoint"),
        )
        for v in raw
    ]


def _parse_networks(raw: list[dict]) -> list[DockerNetwork]:
    return [
        DockerNetwork(
            id=n.get("ID", ""),
            name=n.get("Name", ""),
            driver=n.get("Driver", ""),
            scope=n.get("Scope", ""),
        )
        for n in raw
    ]


def _parse_stacks(raw: list[dict]) -> list[DockerComposeStack]:
    return [
        DockerComposeStack(
            name=s.get("Name", s.get("name", "")),
            status=s.get("Status", s.get("status", "")),
            config_files=s.get("ConfigFiles", s.get("configFiles")),
        )
        for s in raw
    ]

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Ollama server CRUD with model discovery, GPU status, and model preloading."""

import asyncio
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import OllamaServer, RoleAssignment
from backend.repositories.ollama_server_repo import OllamaServerRepository
from backend.schemas import (
    GpuStatusResponse,
    OllamaServerCreate,
    OllamaServerOut,
    OllamaServerUpdate,
    PreloadRequest,
    PreloadResult,
    RunningModelsResponse,
    UnloadRequest,
)
from backend.services.http_client import get_http_client

router = APIRouter(tags=["ollama-servers"])


def _get_repo(db: AsyncSession = Depends(get_db)) -> OllamaServerRepository:
    return OllamaServerRepository(db)


async def _fetch_models(url: str) -> tuple[str, list[dict] | None, str | None]:
    """Fetch models from Ollama API. Returns (status, models, error)."""
    client = get_http_client()
    try:
        resp = await client.get(f"{url.rstrip('/')}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = data.get("models", [])
        return "online", models, None
    except httpx.HTTPError as exc:
        return "error", None, str(exc)
    except Exception as exc:
        return "error", None, str(exc)


async def _fetch_running(url: str) -> tuple[str, list[dict], str | None]:
    """Fetch running models from Ollama /api/ps. Returns (status, models, error)."""
    client = get_http_client()
    try:
        resp = await client.get(f"{url.rstrip('/')}/api/ps", timeout=10)
        resp.raise_for_status()
        return "online", resp.json().get("models", []), None
    except Exception as exc:
        return "error", [], str(exc)


@router.get("/ollama-servers", response_model=list[OllamaServerOut])
async def list_ollama_servers(repo: OllamaServerRepository = Depends(_get_repo)):
    return await repo.list_all()


@router.get("/ollama-servers/gpu-status", response_model=GpuStatusResponse)
async def get_gpu_status(repo: OllamaServerRepository = Depends(_get_repo)):
    """Fetch running models from all registered Ollama servers in parallel."""
    servers = await repo.list_all()

    async def _status_for(server: OllamaServer) -> dict:
        status, models, error = await _fetch_running(server.url)
        return {
            "server_id": server.id,
            "server_name": server.name,
            "server_url": server.url,
            "status": status,
            "models": models,
            "error": error,
        }

    results = await asyncio.gather(*[_status_for(s) for s in servers])
    return {"servers": list(results)}


@router.post("/ollama-servers", response_model=OllamaServerOut, status_code=201)
async def create_ollama_server(
    body: OllamaServerCreate,
    repo: OllamaServerRepository = Depends(_get_repo),
):
    server = OllamaServer(**body.model_dump())

    # Health check + fetch models
    status, models, error = await _fetch_models(body.url)
    server.status = status
    server.cached_models = models
    server.error_message = error
    if status == "online":
        server.last_seen_at = datetime.now(UTC)

    return await repo.create(server)


@router.get("/ollama-servers/{server_id}", response_model=OllamaServerOut)
async def get_ollama_server(
    server_id: int,
    repo: OllamaServerRepository = Depends(_get_repo),
):
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Ollama server not found")
    return server


@router.put("/ollama-servers/{server_id}", response_model=OllamaServerOut)
async def update_ollama_server(
    server_id: int,
    body: OllamaServerUpdate,
    repo: OllamaServerRepository = Depends(_get_repo),
):
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Ollama server not found")
    return await repo.update(server, body.model_dump(exclude_unset=True))


@router.delete("/ollama-servers/{server_id}", status_code=204)
async def delete_ollama_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
):
    repo = OllamaServerRepository(db)
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Ollama server not found")
    # Check if any role assignments reference this server (avoid lazy load)
    role_count = (
        await db.execute(
            select(func.count(RoleAssignment.id)).where(
                RoleAssignment.ollama_server_id == server_id
            )
        )
    ).scalar_one()
    if role_count > 0:
        raise HTTPException(
            409,
            "Cannot delete server with active role assignments. Remove role assignments first.",
        )
    await repo.delete(server)


@router.post("/ollama-servers/{server_id}/refresh-models", response_model=OllamaServerOut)
async def refresh_ollama_models(
    server_id: int,
    repo: OllamaServerRepository = Depends(_get_repo),
):
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Ollama server not found")

    status, models, error = await _fetch_models(server.url)
    data = {"status": status, "cached_models": models, "error_message": error}
    if status == "online":
        data["last_seen_at"] = datetime.now(UTC)
    return await repo.update(server, data)


@router.get(
    "/ollama-servers/{server_id}/running",
    response_model=RunningModelsResponse,
)
async def get_running_models(
    server_id: int,
    repo: OllamaServerRepository = Depends(_get_repo),
):
    """Get currently running/loaded models for a specific Ollama server."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Ollama server not found")

    status, models, error = await _fetch_running(server.url)
    return {
        "server_id": server.id,
        "server_name": server.name,
        "server_url": server.url,
        "status": status,
        "models": models,
        "error": error,
    }


@router.post(
    "/ollama-servers/{server_id}/preload",
    response_model=PreloadResult,
)
async def preload_model(
    server_id: int,
    body: PreloadRequest,
    repo: OllamaServerRepository = Depends(_get_repo),
):
    """Preload a model into GPU/CPU memory on the Ollama server."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Ollama server not found")

    client = get_http_client()
    try:
        resp = await client.post(
            f"{server.url.rstrip('/')}/api/generate",
            json={
                "model": body.model,
                "keep_alive": body.keep_alive,
                "prompt": "",
                "stream": False,
            },
            timeout=300.0,
        )
        resp.raise_for_status()
        return {"success": True, "model": body.model, "error": None}
    except Exception as exc:
        return {"success": False, "model": body.model, "error": str(exc)}


@router.post(
    "/ollama-servers/{server_id}/unload",
    response_model=PreloadResult,
)
async def unload_model(
    server_id: int,
    body: UnloadRequest,
    repo: OllamaServerRepository = Depends(_get_repo),
):
    """Unload a model from memory on the Ollama server."""
    server = await repo.get_by_id(server_id)
    if not server:
        raise HTTPException(404, "Ollama server not found")

    client = get_http_client()
    try:
        resp = await client.post(
            f"{server.url.rstrip('/')}/api/generate",
            json={
                "model": body.model,
                "keep_alive": 0,
                "prompt": "",
                "stream": False,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return {"success": True, "model": body.model, "error": None}
    except Exception as exc:
        return {"success": False, "model": body.model, "error": str(exc)}
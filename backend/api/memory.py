# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""API endpoints for org-level memory and Obsidian sync."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.http_client import get_http_client
from backend.services.memory.obsidian_sync import ObsidianSyncService
from backend.services.memory.org_memory import VALID_NAMESPACES, OrgMemoryService

logger = logging.getLogger("agentickode.api.memory")
router = APIRouter(tags=["memory"])


class MemoryStoreRequest(BaseModel):
    content: str
    namespace: str = "general"
    metadata: dict = {}


class MemoryQueryRequest(BaseModel):
    query_texts: list[str]
    namespaces: list[str] | None = None
    n_results: int = 5


class ObsidianSyncRequest(BaseModel):
    api_url: str = ""
    api_key: str = ""
    folder: str = "/"


@router.post("/memory/store")
async def store_memory(body: MemoryStoreRequest):
    """Store a knowledge document in org memory."""
    client = get_http_client()
    service = OrgMemoryService(client)
    doc_id = await service.store(body.content, body.namespace, body.metadata)
    return {"status": "stored", "doc_id": doc_id}


@router.post("/memory/query")
async def query_memory(body: MemoryQueryRequest):
    """Query org memory for relevant knowledge."""
    client = get_http_client()
    service = OrgMemoryService(client)
    results = await service.query(body.query_texts, body.namespaces, body.n_results)
    return {"results": results, "count": len(results)}


@router.get("/memory/namespaces")
async def list_namespaces():
    """List available memory namespaces."""
    return {"namespaces": sorted(VALID_NAMESPACES)}


@router.post("/memory/sync-obsidian")
async def sync_obsidian(body: ObsidianSyncRequest):
    """Read markdown files from an Obsidian vault and store in org memory."""
    client = get_http_client()
    obsidian = ObsidianSyncService(client, body.api_url, body.api_key)
    memory = OrgMemoryService(client)

    files = await obsidian.list_files(body.folder)
    stored = 0
    for file_path in files:
        content = await obsidian.read_file(file_path)
        if not content:
            continue

        sections = obsidian.split_by_headings(content, file_path)
        for section in sections:
            doc_id = await memory.store(
                content=f"# {section['heading']}\n\n{section['content']}",
                namespace="general",
                metadata={"source": "obsidian", "path": file_path, "heading": section["heading"]},
            )
            if doc_id:
                stored += 1

    return {"status": "synced", "files_read": len(files), "sections_stored": stored}

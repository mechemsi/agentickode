# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""MCP tools for org-level memory and knowledge management."""

from fastmcp import Context

from backend.mcp.tools.projects import _api


async def query_org_memory(
    ctx: Context,
    query_texts: list[str],
    namespaces: list[str] | None = None,
    n_results: int = 5,
) -> dict:
    """Search organizational memory for relevant knowledge.

    Use this to check if the org has encountered similar issues before,
    or to find established patterns and architectural decisions.

    Args:
        query_texts: Search queries describing what you're looking for.
        namespaces: Filter by namespace (decisions, patterns, errors, architecture, conventions).
        n_results: Maximum results to return.

    Returns:
        Matching knowledge documents with content and metadata.
    """
    return await _api(
        ctx,
        "post",
        "/memory/query",
        json={"query_texts": query_texts, "namespaces": namespaces, "n_results": n_results},
    )


async def store_knowledge(
    ctx: Context,
    content: str,
    namespace: str = "general",
    metadata: dict | None = None,
) -> dict:
    """Store a new knowledge document in organizational memory.

    Use this to record important decisions, patterns, or learnings
    that should persist across projects and runs.

    Args:
        content: The knowledge to store (markdown text).
        namespace: Category — one of: decisions, patterns, errors, architecture, conventions, general.
        metadata: Additional metadata (project_id, run_id, etc.).

    Returns:
        Status and document ID.
    """
    return await _api(
        ctx,
        "post",
        "/memory/store",
        json={"content": content, "namespace": namespace, "metadata": metadata or {}},
    )


async def sync_obsidian_vault(
    ctx: Context,
    api_url: str = "",
    api_key: str = "",
    folder: str = "/",
) -> dict:
    """Sync an Obsidian vault into organizational memory.

    Reads markdown files from the vault and stores each section
    as a searchable knowledge document.

    Args:
        api_url: Obsidian Local REST API URL (default: http://localhost:27124).
        api_key: API key for the Obsidian REST API plugin.
        folder: Vault folder to sync (default: root).

    Returns:
        Sync status with files read and sections stored.
    """
    return await _api(
        ctx,
        "post",
        "/memory/sync-obsidian",
        json={"api_url": api_url, "api_key": api_key, "folder": folder},
    )

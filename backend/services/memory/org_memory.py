# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Org-level memory service — cross-project knowledge via ChromaDB."""

import logging
import uuid

import httpx

from backend.config import settings

logger = logging.getLogger("agentickode.memory.org")

VALID_NAMESPACES = {"decisions", "patterns", "errors", "architecture", "conventions", "general"}
_COLLECTION = "org_memory"


class OrgMemoryService:
    """Store and query cross-project organizational knowledge."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._base_url = settings.chromadb_url.rstrip("/") if settings.chromadb_url else ""

    async def store(
        self,
        content: str,
        namespace: str = "general",
        metadata: dict | None = None,
    ) -> str:
        """Store a knowledge document in org memory.

        Returns the document ID.
        """
        if not self._base_url:
            logger.debug("ChromaDB not configured, skipping org memory store")
            return ""

        doc_id = str(uuid.uuid4())
        meta = {"namespace": namespace, **(metadata or {})}

        try:
            await self._client.post(
                f"{self._base_url}/api/v1/collections/{_COLLECTION}/add",
                json={
                    "ids": [doc_id],
                    "documents": [content],
                    "metadatas": [meta],
                },
            )
            return doc_id
        except Exception:
            logger.exception("Failed to store org memory")
            return ""

    async def query(
        self,
        query_texts: list[str],
        namespaces: list[str] | None = None,
        n_results: int = 5,
    ) -> list[dict]:
        """Query org memory for relevant knowledge.

        Returns list of {content, metadata, distance} dicts.
        """
        if not self._base_url:
            return []

        where_filter = None
        if namespaces:
            where_filter = {"namespace": {"$in": namespaces}}

        try:
            resp = await self._client.post(
                f"{self._base_url}/api/v1/collections/{_COLLECTION}/query",
                json={
                    "query_texts": query_texts,
                    "n_results": n_results,
                    **({"where": where_filter} if where_filter else {}),
                },
            )
            data = resp.json()
            results = []
            documents = data.get("documents", [[]])[0]
            metadatas = data.get("metadatas", [[]])[0]
            distances = data.get("distances", [[]])[0]
            for doc, meta, dist in zip(documents, metadatas, distances, strict=False):
                results.append({"content": doc, "metadata": meta, "distance": dist})
            return results
        except Exception:
            logger.exception("Failed to query org memory")
            return []

    async def store_run_learnings(self, learnings: list[dict]) -> int:
        """Store multiple learnings from a completed run.

        Each learning: {"content": str, "namespace": str, "metadata": dict}
        Returns count of stored documents.
        """
        stored = 0
        for learning in learnings:
            doc_id = await self.store(
                content=learning["content"],
                namespace=learning.get("namespace", "general"),
                metadata=learning.get("metadata", {}),
            )
            if doc_id:
                stored += 1
        return stored

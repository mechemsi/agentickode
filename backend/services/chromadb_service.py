# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""ChromaDB service — class-based replacement for chromadb_client.py."""

import logging

import httpx

from backend.config import settings

logger = logging.getLogger("agentickode.chromadb")


class ChromaDBService:
    """Client for the ChromaDB vector database API."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = "", token: str = ""):
        self._client = client
        self._base_url = base_url or settings.chromadb_url
        self._token = token or settings.chromadb_token

    async def query_project_context(
        self, project_id: str, texts: list[str], n_results: int = 5
    ) -> list[str]:
        """Query ChromaDB for relevant project context documents."""
        try:
            resp = await self._client.post(
                f"{self._base_url}/api/v1/collections/projects/query",
                json={
                    "query_texts": texts,
                    "n_results": n_results,
                    "where": {"project_id": project_id},
                },
                headers={"X-Chroma-Token": self._token},
                timeout=30.0,
            )
            if resp.status_code == 200:
                return resp.json().get("documents", [[]])[0]
            logger.warning(
                "ChromaDB returned %s for project %s",
                resp.status_code,
                project_id,
            )
        except Exception:
            logger.warning(
                "ChromaDB query failed for project %s",
                project_id,
                exc_info=True,
            )
        return []

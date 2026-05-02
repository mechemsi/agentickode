# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Notion TaskManager — bidirectional page status sync via a Status select property."""

import logging

import httpx

logger = logging.getLogger("agentickode.task_management.notion")

_NOTION_BASE_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"

# Default mapping from internal lifecycle state → Notion Status select option.
_DEFAULT_STATUS_MAP = {
    "in_progress": "In Progress",
    "done": "Done",
    "failed": "Blocked",
}


class NotionTaskManager:
    """Bidirectional Notion TaskManager: update Status, post comments, create pages."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        status_map: dict[str, str] | None = None,
        status_property: str = "Status",
        title_property: str = "Name",
    ):
        self._client = client
        self._api_key = api_key
        self._status_map = {**_DEFAULT_STATUS_MAP, **(status_map or {})}
        self._status_property = status_property
        self._title_property = title_property

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _resolve_page_id(self, meta: dict) -> str:
        return meta.get("page_id") or meta.get("id") or ""

    async def update_status(self, meta: dict, status: str) -> None:
        page_id = self._resolve_page_id(meta)
        target = self._status_map.get(status)
        if not page_id or not target:
            return

        status_property = meta.get("status_property") or self._status_property
        url = f"{_NOTION_BASE_URL}/pages/{page_id}"
        payload = {
            "properties": {
                status_property: {"select": {"name": target}},
            }
        }
        resp = await self._client.patch(url, headers=self._headers(), json=payload, timeout=15)
        if resp.status_code >= 400:
            logger.warning(
                "Notion page %s status update failed: %s %s",
                page_id,
                resp.status_code,
                resp.text[:200],
            )
        else:
            logger.info("Notion page %s → %s", page_id, target)

    async def add_comment(self, meta: dict, body: str) -> None:
        page_id = self._resolve_page_id(meta)
        if not page_id:
            return
        url = f"{_NOTION_BASE_URL}/comments"
        payload = {
            "parent": {"page_id": page_id},
            "rich_text": [{"type": "text", "text": {"content": body}}],
        }
        resp = await self._client.post(url, headers=self._headers(), json=payload, timeout=15)
        if resp.status_code >= 400:
            logger.warning(
                "Notion comment on %s failed: %s %s",
                page_id,
                resp.status_code,
                resp.text[:200],
            )

    async def create_issue(
        self, project_ref: str, title: str, body: str, labels: list[str] | None = None
    ) -> dict:
        """Create a page inside a Notion database. project_ref = database_id."""
        if not project_ref:
            return {"id": "", "url": ""}
        url = f"{_NOTION_BASE_URL}/pages"
        properties: dict = {
            self._title_property: {
                "title": [{"type": "text", "text": {"content": title}}],
            }
        }
        if labels:
            properties["Tags"] = {
                "multi_select": [{"name": lbl} for lbl in labels],
            }
        payload = {
            "parent": {"database_id": project_ref},
            "properties": properties,
        }
        if body:
            payload["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": body}}],
                    },
                }
            ]

        resp = await self._client.post(url, headers=self._headers(), json=payload, timeout=30)
        if resp.status_code >= 400:
            logger.warning("Notion page create failed: %s %s", resp.status_code, resp.text[:200])
            return {"id": "", "url": ""}
        data = resp.json()
        return {"id": data.get("id", ""), "url": data.get("url", "")}

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Polls a Notion database and creates TaskRuns for pages tagged ai-task.

Expected ``project.integration_config``:

- ``notion_api_key_enc`` — Fernet-encrypted Notion integration token
- ``notion_database_id`` — database to poll
- ``notion_status_property`` (default: ``"Status"``) — select property name
- ``notion_tag_property`` (default: ``"Tags"``) — multi_select property name
- ``notion_ai_task_tag`` (default: ``"ai-task"``) — required tag value
- ``notion_use_claude_tag`` (default: ``"use-claude"``) — optional tag that flips ``use_claude``
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ProjectConfig
from backend.services.encryption import decrypt_value
from backend.services.http_client import get_http_client
from backend.services.run_factory import create_task_run
from backend.services.task_source_polling._dedupe import existing_task_ids

logger = logging.getLogger("agentickode.polling.notion")

_NOTION_BASE_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _resolve_notion_api_key(project: ProjectConfig) -> str | None:
    cfg = project.integration_config or {}
    enc = cfg.get("notion_api_key_enc")
    if enc:
        try:
            return decrypt_value(enc)
        except Exception:
            logger.exception("Failed to decrypt notion_api_key for %s", project.project_id)
            return None
    return cfg.get("notion_api_key")  # plaintext fallback


def _extract_plain_text(rich_text_list: list | None) -> str:
    if not rich_text_list:
        return ""
    return "".join(chunk.get("plain_text", "") for chunk in rich_text_list)


def _title_from_page(page: dict, title_property: str = "Name") -> str:
    props = page.get("properties", {})
    # Try the requested title property first, then any property of type "title".
    for prop_name in (title_property, *[p for p in props]):
        prop = props.get(prop_name)
        if isinstance(prop, dict) and prop.get("type") == "title":
            return _extract_plain_text(prop.get("title", []))
    return ""


def _multi_select_values(prop: dict | None) -> list[str]:
    if not isinstance(prop, dict):
        return []
    return [opt.get("name", "") for opt in prop.get("multi_select", []) or []]


class NotionPagePoller:
    """Queries a Notion database for open ai-task pages and dispatches TaskRuns."""

    async def poll(self, project: ProjectConfig, session: AsyncSession) -> list[int]:
        cfg = project.integration_config or {}
        database_id = cfg.get("notion_database_id")
        if not database_id:
            return []

        api_key = _resolve_notion_api_key(project)
        if not api_key:
            logger.debug("Skipping Notion poll for %s: no API key", project.project_id)
            return []

        tag_property = cfg.get("notion_tag_property", "Tags")
        ai_task_tag = cfg.get("notion_ai_task_tag", "ai-task")
        use_claude_tag = cfg.get("notion_use_claude_tag", "use-claude")
        title_property = cfg.get("notion_title_property", "Name")
        status_property = cfg.get("notion_status_property", "Status")

        client = get_http_client()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }
        query_url = f"{_NOTION_BASE_URL}/databases/{database_id}/query"
        query_body: dict = {
            "filter": {
                "property": tag_property,
                "multi_select": {"contains": ai_task_tag},
            },
            "page_size": 50,
        }

        try:
            resp = await client.post(query_url, headers=headers, json=query_body, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Notion poll failed for %s: %s", project.project_id, exc)
            return []

        data = resp.json()
        pages = data.get("results", [])
        if not isinstance(pages, list) or not pages:
            return []

        task_ids = [p.get("id", "") for p in pages if p.get("id")]
        already = await existing_task_ids(session, project.project_id, "notion", task_ids)

        created: list[int] = []
        for page in pages:
            page_id = page.get("id", "")
            if not page_id or page_id in already:
                continue
            props = page.get("properties", {})
            status_prop = props.get(status_property) or {}
            status_value = ""
            if isinstance(status_prop, dict):
                select_val = status_prop.get("select") or status_prop.get("status")
                if isinstance(select_val, dict):
                    status_value = select_val.get("name", "")
            # Skip pages already marked done
            if status_value.lower() in {"done", "completed"}:
                continue

            tags = _multi_select_values(props.get(tag_property))
            title = _title_from_page(page, title_property)
            run = create_task_run(
                task_id=page_id,
                project=project,
                title=title,
                description=page.get("url", ""),
                task_source="notion",
                task_source_meta={
                    "database_id": database_id,
                    "page_id": page_id,
                    "url": page.get("url", ""),
                    "tags": tags,
                    "status": status_value,
                    "status_property": status_property,
                    "title_property": title_property,
                    "event": "polled",
                },
                use_claude=use_claude_tag in tags,
            )
            session.add(run)
            await session.flush()
            created.append(run.id)
            logger.info("Notion poll: created run #%d for page %s", run.id, page_id)
        return created

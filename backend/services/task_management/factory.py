# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Factory for creating TaskManager instances by task source."""

import logging

import httpx

from backend.config import settings
from backend.models import ProjectConfig
from backend.services.encryption import decrypt_value
from backend.services.task_management.github_manager import GitHubTaskManager
from backend.services.task_management.linear_manager import LinearTaskManager
from backend.services.task_management.notion_manager import NotionTaskManager
from backend.services.task_management.plane_manager import PlaneTaskManager
from backend.services.task_management.protocol import TaskManager

logger = logging.getLogger("agentickode.task_management.factory")


class NoOpTaskManager:
    """Fallback for sources without bidirectional support."""

    async def update_status(self, meta: dict, status: str) -> None:
        pass

    async def add_comment(self, meta: dict, body: str) -> None:
        pass

    async def create_issue(
        self, project_ref: str, title: str, body: str, labels: list[str] | None = None
    ) -> dict:
        return {"id": "", "url": ""}


_noop = NoOpTaskManager()


def _notion_from_project(
    project: ProjectConfig | None, client: httpx.AsyncClient
) -> TaskManager | None:
    cfg = (project.integration_config if project else {}) or {}
    enc = cfg.get("notion_api_key_enc")
    api_key = cfg.get("notion_api_key")
    if enc and not api_key:
        try:
            api_key = decrypt_value(enc)
        except Exception:
            logger.exception("Failed to decrypt notion_api_key")
            return None
    if not api_key:
        return None
    return NotionTaskManager(
        client,
        api_key,
        status_map=cfg.get("notion_status_map"),
        status_property=cfg.get("notion_status_property", "Status"),
        title_property=cfg.get("notion_title_property", "Name"),
    )


def get_task_manager(
    task_source: str,
    client: httpx.AsyncClient,
    project: ProjectConfig | None = None,
) -> TaskManager:
    """Return the appropriate TaskManager for the given task source.

    ``project`` is optional — pass it when per-project secrets
    (e.g. Notion API key) are needed.
    """
    if task_source == "github" and settings.github_token:
        return GitHubTaskManager(
            client, settings.github_token, settings.github_api_url or "https://api.github.com"
        )
    if (
        task_source == "plane"
        and getattr(settings, "plane_api_url", "")
        and getattr(settings, "plane_api_key", "")
    ):
        return PlaneTaskManager(client, settings.plane_api_url, settings.plane_api_key)
    if task_source == "linear" and getattr(settings, "linear_api_key", ""):
        return LinearTaskManager(client, settings.linear_api_key)
    if task_source == "notion":
        manager = _notion_from_project(project, client)
        if manager is not None:
            return manager
    return _noop  # type: ignore[return-value]

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Factory for creating TaskManager instances by task source."""

import httpx

from backend.config import settings
from backend.services.task_management.github_manager import GitHubTaskManager
from backend.services.task_management.linear_manager import LinearTaskManager
from backend.services.task_management.plane_manager import PlaneTaskManager
from backend.services.task_management.protocol import TaskManager


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


def get_task_manager(task_source: str, client: httpx.AsyncClient) -> TaskManager:
    """Return the appropriate TaskManager for the given task source."""
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
    return _noop  # type: ignore[return-value]

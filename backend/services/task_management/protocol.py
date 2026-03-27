# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""TaskManager protocol — interface for bidirectional task management."""

from typing import Protocol


class TaskManager(Protocol):
    """Bidirectional interface for external task/issue trackers."""

    async def update_status(self, meta: dict, status: str) -> None:
        """Update the external issue/task status.

        Args:
            meta: task_source_meta dict from the TaskRun.
            status: One of "in_progress", "done", "failed".
        """
        ...

    async def add_comment(self, meta: dict, body: str) -> None:
        """Post a comment on the external issue/task.

        Args:
            meta: task_source_meta dict from the TaskRun.
            body: Comment text (markdown).
        """
        ...

    async def create_issue(
        self, project_ref: str, title: str, body: str, labels: list[str] | None = None
    ) -> dict:
        """Create a new issue in the external tracker.

        Args:
            project_ref: Project identifier (repo path, workspace slug, etc.).
            title: Issue title.
            body: Issue description.
            labels: Optional labels to apply.

        Returns:
            Dict with at least "id" and "url" of the created issue.
        """
        ...

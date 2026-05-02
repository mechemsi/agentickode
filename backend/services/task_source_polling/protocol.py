# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""IssuePoller Protocol — pull open issues and create TaskRuns."""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ProjectConfig


class IssuePoller(Protocol):
    """Fetches open issues from an external tracker and dispatches TaskRuns.

    Implementations must be idempotent: repeated polls for the same external
    issue must NOT create duplicate ``TaskRun`` rows. Dedupe on the tuple
    ``(project_id, task_source, task_id)``.
    """

    async def poll(self, project: ProjectConfig, session: AsyncSession) -> list[int]:
        """Fetch open issues and create TaskRuns for any that are new.

        Returns the list of newly-created ``TaskRun.id`` values.
        """
        ...

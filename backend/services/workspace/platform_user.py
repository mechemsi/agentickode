# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Resolve the run-as OS user for the local 'platform' workspace server.

The platform server runs commands inside the backend container (as root). When
its ``worker_user`` is configured, terminal/chat/agent launches should run as
that user via ``runuser``. Returns ``None`` when unset → callers fall through to
the pre-existing root behaviour (no regression).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import WorkspaceServer


async def get_platform_run_as_user(db: AsyncSession) -> str | None:
    """Return ``worker_user`` for the local platform server, or ``None``."""
    result = await db.execute(
        select(WorkspaceServer.worker_user).where(WorkspaceServer.server_type == "local").limit(1)
    )
    return result.scalar_one_or_none()

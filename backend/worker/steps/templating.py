# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Minimal placeholder substitution for flow-prompt text.

Supports one pattern only — no Jinja, no eval:
- ``{{run.FIELD}}`` -> ``getattr(task_run, FIELD, "")``
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun

logger = logging.getLogger(__name__)

RUN_FIELD = re.compile(r"\{\{run\.(\w+)\}\}")


async def render(template_str: str, task_run: TaskRun, session: AsyncSession) -> str:
    """Substitute ``{{run.X}}`` placeholders with the run's field values."""

    def _run_sub(match: re.Match[str]) -> str:
        value = getattr(task_run, match.group(1), "")
        return "" if value is None else str(value)

    return RUN_FIELD.sub(_run_sub, template_str)

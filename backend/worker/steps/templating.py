# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Minimal placeholder substitution for step commands and prompts.

Supports two patterns only — no Jinja, no eval:
- ``{{run.FIELD}}``           -> ``getattr(task_run, FIELD, "")``
- ``{{steps.NAME.FIELD}}``    -> latest completed PhaseExecution.result[FIELD]
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PhaseExecution, TaskRun

logger = logging.getLogger(__name__)

RUN_FIELD = re.compile(r"\{\{run\.(\w+)\}\}")
STEP_FIELD = re.compile(r"\{\{steps\.([\w-]+)\.(\w+)\}\}")


async def _lookup_step_field(session: AsyncSession, run_id: int, name: str, field: str) -> str:
    stmt = (
        select(PhaseExecution)
        .where(PhaseExecution.run_id == run_id)
        .where(PhaseExecution.phase_name == name)
        .where(PhaseExecution.status == "completed")
        .order_by(PhaseExecution.completed_at.desc())
        .limit(1)
    )
    pe = (await session.execute(stmt)).scalar_one_or_none()
    if pe is None or not isinstance(pe.result, dict) or field not in pe.result:
        logger.warning(
            "templating: no completed step %r with field %r for run %s", name, field, run_id
        )
        return ""
    return str(pe.result[field])


async def render(template_str: str, task_run: TaskRun, session: AsyncSession) -> str:
    """Substitute ``{{run.X}}`` and ``{{steps.NAME.FIELD}}`` placeholders."""

    def _run_sub(match: re.Match[str]) -> str:
        value = getattr(task_run, match.group(1), "")
        return "" if value is None else str(value)

    out = RUN_FIELD.sub(_run_sub, template_str)

    # Step lookups need DB access, so do them sequentially.
    for match in list(STEP_FIELD.finditer(out)):
        value = await _lookup_step_field(session, task_run.id, match.group(1), match.group(2))
        out = out.replace(match.group(0), value, 1)
    return out

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Per-flow-type data fetching for flow prompts (ADR-009).

Each ``flow_type`` has a FIXED set of data sources that the platform always
fetches (OQ-2); a flow prompt may DECLARE extra sources via ``extra_data_sources``.
A source is a named async fetcher registered in ``SOURCE_FETCHERS``. Unknown or
failing sources are skipped (logged), never fatal — the agent still gets whatever
was gathered.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import FlowPrompt, TaskRun
from backend.services.container import ServiceContainer

logger = logging.getLogger("agentickode.flow.data_sources")

# Fixed sources per flow type. Extra per-prompt sources are appended (deduped).
FLOW_TYPE_SOURCES: dict[str, list[str]] = {
    "implement": ["repo_context", "issue_body"],
    "pr_review": ["pr_diff"],
}

Fetcher = Callable[[TaskRun, AsyncSession, ServiceContainer], Awaitable[Any]]


async def _repo_context(run: TaskRun, session: AsyncSession, services: ServiceContainer) -> dict:
    """Basic repo + task context from the run (no external calls)."""
    return {
        "repo": f"{run.repo_owner}/{run.repo_name}",
        "default_branch": run.default_branch,
        "branch": run.branch_name,
        "title": run.title,
        "description": run.description,
    }


async def _issue_body(run: TaskRun, session: AsyncSession, services: ServiceContainer) -> Any:
    """The originating issue/task body, if captured in task_source_meta."""
    meta = run.task_source_meta or {}
    return meta.get("issue_body") or meta.get("body") or run.description


async def _pr_diff(run: TaskRun, session: AsyncSession, services: ServiceContainer) -> Any:
    """PR diff + comments. Reuses the existing pr_fetch phase, which writes the
    diff into ``run.coding_results``; we then return that payload."""
    from backend.worker.phases import pr_fetch

    await pr_fetch.run(run, session, services, None)
    return run.coding_results


SOURCE_FETCHERS: dict[str, Fetcher] = {
    "repo_context": _repo_context,
    "issue_body": _issue_body,
    "pr_diff": _pr_diff,
}


def sources_for(flow: FlowPrompt) -> list[str]:
    """Fixed sources for the flow's type plus any declared extras, deduped in order."""
    out: list[str] = list(FLOW_TYPE_SOURCES.get(str(flow.flow_type), []))
    for s in flow.extra_data_sources or []:
        if s and s not in out:
            out.append(s)
    return out


async def fetch_flow_data(
    run: TaskRun, session: AsyncSession, services: ServiceContainer, flow: FlowPrompt
) -> dict[str, Any]:
    """Gather all data sources for a flow prompt into ``{source: value}``."""
    data: dict[str, Any] = {}
    for name in sources_for(flow):
        fetcher = SOURCE_FETCHERS.get(name)
        if fetcher is None:
            logger.warning("Unknown flow data source %r — skipping", name)
            continue
        try:
            data[name] = await fetcher(run, session, services)
        except Exception:
            logger.warning("Flow data source %r failed — skipping", name, exc_info=True)
    return data

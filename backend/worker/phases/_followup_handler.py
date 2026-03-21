# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Follow-up task handler for the autonomous agent loop.

After a run completes, this module:
  1. Reads .autodev/follow_up_tasks.json and creates child TaskRun records
  2. Evaluates threshold_rules from autonomy_config and creates tasks when breached
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.worker.broadcaster import broadcaster
from backend.worker.phases._context_builder import read_workspace_json
from backend.worker.phases._helpers import get_ssh_for_run

logger = logging.getLogger("agentickode.phases.followup_handler")

# Maximum depth of agent-initiated follow-up chains to prevent runaway task creation
_DEFAULT_MAX_DEPTH = 2


async def process_followup_tasks(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    *,
    autonomy_config: dict | None = None,
) -> None:
    """Read follow_up_tasks.json from workspace and create child TaskRuns.
    Then evaluate threshold_rules.
    """
    config = autonomy_config or {}
    if not config.get("allow_agent_followups", False):
        return

    if not await _check_depth_limit(task_run, session, config):
        return

    followup_data = await _read_followup_file(task_run, session)
    await _create_followup_runs(task_run, session, followup_data)

    threshold_rules = config.get("threshold_rules", [])
    if threshold_rules:
        await _evaluate_threshold_rules(task_run, session, threshold_rules)


async def _check_depth_limit(task_run: TaskRun, session: AsyncSession, config: dict) -> bool:
    """Return True if the run is within the allowed follow-up depth, False if limit reached."""
    max_depth = int(config.get("max_followup_depth", _DEFAULT_MAX_DEPTH))
    current_depth = await _get_followup_depth(task_run, session)
    if current_depth < max_depth:
        return True
    await broadcaster.log(
        task_run.id,
        f"Follow-up depth limit reached ({current_depth}/{max_depth}), skipping",
        level="warning",
        phase="agent_loop",
    )
    return False


async def _read_followup_file(task_run: TaskRun, session: AsyncSession) -> list | None:
    """Read .autodev/follow_up_tasks.json from the workspace. Returns list or None."""
    try:
        ssh = await get_ssh_for_run(task_run, session)
        workspace = task_run.workspace_path or ""
        data = await read_workspace_json(ssh, workspace, ".autodev/follow_up_tasks.json")
        return data if isinstance(data, list) else None
    except Exception:
        logger.debug("Could not read follow_up_tasks.json for run #%s", task_run.id, exc_info=True)
        return None


async def _create_followup_runs(
    task_run: TaskRun,
    session: AsyncSession,
    followup_data: list | None,
) -> None:
    """Create child TaskRuns from agent-proposed follow-up items and persist them."""
    if not followup_data:
        return

    task_run.follow_up_tasks = followup_data
    await session.commit()

    created_count = 0
    for item in followup_data[:10]:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "Follow-up task")
        if not title:
            continue
        child_run = await _create_child_run(
            task_run, session, title=title, description=item.get("description", "")
        )
        created_count += 1
        logger.info("Created follow-up task #%s '%s' for parent run #%s", child_run.id, title, task_run.id)

    if created_count:
        await broadcaster.log(
            task_run.id,
            f"Created {created_count} agent-proposed follow-up task(s)",
            phase="agent_loop",
        )


async def _evaluate_threshold_rules(
    task_run: TaskRun,
    session: AsyncSession,
    rules: list[dict],
) -> None:
    """Check threshold rules against run result metrics and create tasks if breached."""
    result = task_run.coding_results or {}
    metrics = {
        "test_coverage": result.get("coverage_pct"),
        "lint_errors": result.get("lint_error_count"),
        "test_failures": result.get("test_failures"),
    }

    for rule in rules:
        metric = rule.get("metric")
        operator = rule.get("operator")
        threshold = rule.get("value")
        task_template = rule.get("task", "")

        if metric not in metrics or metrics[metric] is None:
            continue

        actual = float(metrics[metric])
        breached = _check_threshold(actual, operator, float(threshold))

        if breached:
            title = task_template.format(
                metric=metric,
                value=actual,
                threshold=threshold,
                project_id=task_run.project_id,
            )
            await _create_child_run(
                task_run,
                session,
                title=title,
                description=f"Threshold rule: {metric} {operator} {threshold} (actual: {actual})",
            )
            await broadcaster.log(
                task_run.id,
                f"Threshold rule triggered: {metric}={actual} {operator} {threshold} → created follow-up task",
                phase="agent_loop",
            )


def _check_threshold(actual: float, operator: str, threshold: float) -> bool:
    ops = {
        "<": actual < threshold,
        ">": actual > threshold,
        "==": actual == threshold,
        "<=": actual <= threshold,
        ">=": actual >= threshold,
    }
    return ops.get(operator, False)


async def _get_followup_depth(task_run: TaskRun, session: AsyncSession) -> int:
    """Walk parent_run_id chain to determine current depth of follow-up nesting."""
    depth = 0
    current = task_run
    seen = {current.id}

    while current.parent_run_id is not None:
        parent = await session.get(TaskRun, current.parent_run_id)
        if parent is None or parent.id in seen:
            break
        seen.add(parent.id)
        depth += 1
        current = parent
        if depth > 10:  # safety guard
            break

    return depth


async def _create_child_run(
    parent: TaskRun,
    session: AsyncSession,
    *,
    title: str,
    description: str,
) -> TaskRun:
    """Create a child TaskRun linked to the parent via parent_run_id."""
    child = TaskRun(
        run_type=parent.run_type,
        task_id=str(uuid.uuid4()),
        project_id=parent.project_id,
        title=title,
        description=description,
        branch_name=f"autodev/followup-{uuid.uuid4().hex[:8]}",
        workspace_path=parent.workspace_path,
        repo_owner=parent.repo_owner,
        repo_name=parent.repo_name,
        default_branch=parent.default_branch,
        task_source="agent_followup",
        git_provider=parent.git_provider,
        task_source_meta={"parent_run_id": parent.id},
        workspace_config=parent.workspace_config,
        status="pending",
        parent_run_id=parent.id,
        workflow_template_id=parent.workflow_template_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(child)
    await session.commit()
    await session.refresh(child)
    return child

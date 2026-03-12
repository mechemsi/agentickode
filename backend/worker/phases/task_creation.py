# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase: Task Creation — create child TaskRuns from planner subtasks.

Used by the planner workflow to decompose a task into subtasks
that execute independently as small-task workflows.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.repositories.workflow_template_repo import WorkflowTemplateRepository
from backend.services.container import ServiceContainer
from backend.worker.broadcaster import broadcaster

logger = logging.getLogger("autodev.phases.task_creation")

PHASE_META = {
    "description": "Create child task runs from subtasks",
}


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> dict:
    """Create child TaskRuns from planning_result subtasks."""
    plan = task_run.planning_result or {}
    subtasks = plan.get("subtasks", [])

    if not subtasks:
        await broadcaster.log(
            task_run.id,
            "No subtasks in planning result to create child runs",
            level="warning",
            phase="task_creation",
        )
        return {"children_created": 0}

    # Look up the small-task workflow template
    repo = WorkflowTemplateRepository(session)
    small_task_template = await repo.get_by_name("small-task")
    template_id = small_task_template.id if small_task_template else None

    # Check auto-execute setting from project config
    from backend.repositories.project_config_repo import ProjectConfigRepository

    project_repo = ProjectConfigRepository(session)
    project = await project_repo.get_by_id(task_run.project_id)
    ai_config = (project.ai_config or {}) if project else {}
    auto_execute = ai_config.get("auto_execute_subtasks", True)
    child_status = "pending" if auto_execute else "awaiting_approval"

    created_ids = []
    for i, subtask in enumerate(subtasks):
        title = subtask.get("title", f"Subtask {i + 1}")
        description = subtask.get("description", "")
        files = subtask.get("files_likely_affected", [])

        child = TaskRun(
            task_id=f"{task_run.task_id}-sub-{i + 1}",
            project_id=task_run.project_id,
            title=title,
            description=description,
            branch_name=task_run.branch_name,
            workspace_path=task_run.workspace_path,
            repo_owner=task_run.repo_owner,
            repo_name=task_run.repo_name,
            default_branch=task_run.default_branch,
            task_source=task_run.task_source,
            git_provider=task_run.git_provider,
            task_source_meta=task_run.task_source_meta or {},
            use_claude_api=task_run.use_claude_api,
            workspace_config=task_run.workspace_config,
            parent_run_id=task_run.id,
            workflow_template_id=template_id,
            status=child_status,
            planning_result={
                "subtasks": [
                    {
                        "title": title,
                        "description": description,
                        "files_likely_affected": files,
                    }
                ]
            },
        )
        session.add(child)
        await session.flush()
        created_ids.append(child.id)

        await broadcaster.log(
            task_run.id,
            f"Created child run #{child.id}: {title} (status={child_status})",
            phase="task_creation",
        )

    await session.commit()

    await broadcaster.log(
        task_run.id,
        f"Created {len(created_ids)} child run(s)",
        phase="task_creation",
    )
    return {"children_created": len(created_ids), "child_run_ids": created_ids}
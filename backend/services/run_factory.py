# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Shared factory for creating TaskRun instances from various sources.

Used by webhook handlers, scheduled task executor, monitoring dispatchers,
and messaging command executor.
"""

from backend.models import ProjectConfig, TaskRun


def resolve_workspace_path(project: ProjectConfig, task_id: str) -> str:
    """Determine workspace path based on project config and task ID."""
    ws_cfg = project.workspace_config or {}
    ws_type = ws_cfg.get("workspace_type", "existing")
    if ws_type == "cluster":
        return f"/workspaces/{task_id}"
    if project.workspace_path:
        return str(project.workspace_path)
    return f"/workspaces/{project.project_id}"


def create_task_run(
    task_id: str,
    project: ProjectConfig,
    title: str,
    description: str,
    task_source: str,
    task_source_meta: dict,
    use_claude: bool = False,
    workflow_template_id: int | None = None,
) -> TaskRun:
    """Create a TaskRun from a project config and task details.

    Reused by webhooks, scheduler, monitoring, and messaging sources.

    ``workflow_template_id`` lets the caller pre-bind the run to a template
    resolved via ``TriggerMatcher`` so the pipeline skips its label-match
    fallback.
    """
    execution_mode = "structured"
    if project.autonomy_config and isinstance(project.autonomy_config, dict):
        execution_mode = project.autonomy_config.get("execution_mode", "structured")

    return TaskRun(
        task_id=task_id,
        project_id=project.project_id,
        title=title,
        description=description,
        branch_name=f"feature/ai-{task_id}",
        workspace_path=resolve_workspace_path(project, task_id),
        repo_owner=project.repo_owner,
        repo_name=project.repo_name,
        default_branch=project.default_branch,
        task_source=task_source,
        git_provider=project.git_provider,
        task_source_meta=task_source_meta,
        use_claude_api=use_claude,
        workspace_config=project.workspace_config,
        execution_mode=execution_mode,
        workflow_template_id=workflow_template_id,
    )

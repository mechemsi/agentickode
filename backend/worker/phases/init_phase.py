# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Phase 1: Init — create feature branch + retrieve project context.

Ported from activities.py create_feature_branch + retrieve_project_context.
Git operations execute on the remote workspace server via SSH.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.git import RemoteGitOps
from backend.worker.broadcaster import broadcaster, make_log_metadata
from backend.worker.phases._helpers import get_ssh_for_run

logger = logging.getLogger("agentickode.phases.init")

PHASE_META = {
    "name": "init",
    "description": "Create feature branch and fetch context",
}


async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> None:
    await broadcaster.log(
        task_run.id,
        f"Connecting to workspace server at {task_run.workspace_path}",
        phase="init",
    )
    ssh = await get_ssh_for_run(task_run, session)
    remote_git = RemoteGitOps(ssh)
    await broadcaster.log(task_run.id, f"Connected to {ssh.hostname}:{ssh.port}", phase="init")

    cwd = task_run.workspace_path

    # fix-pr: checkout existing PR branch instead of creating a new one
    meta = task_run.task_source_meta or {}
    pr_branch = meta.get("pr_head_branch")
    if pr_branch:
        await broadcaster.log(task_run.id, f"Checking out PR branch: {pr_branch}", phase="init")
        await remote_git.run_git(["checkout", pr_branch], cwd=cwd)
        await remote_git.run_git(["pull", "origin", pr_branch], cwd=cwd)
        task_run.branch_name = pr_branch
        await broadcaster.log(task_run.id, f"On PR branch {pr_branch}", phase="init")
    else:
        # Normal: create new feature branch from the default branch
        # Defensive checkout — ensure we branch from default_branch, not a leftover branch
        default_branch = str(task_run.default_branch)
        await broadcaster.log(
            task_run.id,
            f"Ensuring on {default_branch} before branching",
            level="debug",
            phase="init",
        )
        try:
            await remote_git.run_git(["checkout", default_branch], cwd=cwd)
        except RuntimeError:
            await broadcaster.log(
                task_run.id,
                f"Could not checkout {default_branch}, branching from current HEAD",
                level="warning",
                phase="init",
            )

        await broadcaster.log(
            task_run.id,
            f"Creating branch: {task_run.branch_name}",
            phase="init",
            metadata=make_log_metadata(
                "ssh_command", command=f"git checkout -b {task_run.branch_name}"
            ),
        )
        try:
            await remote_git.run_git(["checkout", "-b", task_run.branch_name], cwd=cwd)
            await broadcaster.log(task_run.id, "Branch created", phase="init")
        except RuntimeError:
            # Branch may already exist — switch to it
            await remote_git.run_git(["checkout", task_run.branch_name], cwd=cwd)
            await broadcaster.log(
                task_run.id, "Branch already exists, switched to it", phase="init"
            )

    # Retrieve context from ChromaDB (gracefully returns [] if unavailable)
    await broadcaster.log(task_run.id, "Querying ChromaDB for project context", phase="init")
    context_docs = await services.chromadb.query_project_context(
        task_run.project_id,
        [task_run.title, task_run.description],
    )
    await broadcaster.log(
        task_run.id,
        f"Retrieved {len(context_docs)} context documents",
        phase="init",
        metadata=make_log_metadata(
            "response",
            doc_count=len(context_docs),
            doc_previews=[doc[:200] for doc in context_docs[:3]],
        ),
    )

    # Store context in planning_result for next phase to consume
    task_run.planning_result = {"context_docs": context_docs}
    await session.commit()

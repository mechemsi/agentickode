# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Polls GitHub issues for a project and creates TaskRuns for open ai-task issues."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ProjectConfig
from backend.services.encryption import decrypt_value
from backend.services.git.protocol import get_git_provider
from backend.services.http_client import get_http_client
from backend.services.run_factory import create_task_run
from backend.services.task_source_polling._dedupe import existing_task_ids

logger = logging.getLogger("agentickode.polling.github")

_AI_TASK_LABEL = "ai-task"
_USE_CLAUDE_LABEL = "use-claude"


class GitHubIssuePoller:
    """Pulls open GitHub issues labeled ``ai-task`` and dispatches TaskRuns."""

    async def poll(self, project: ProjectConfig, session: AsyncSession) -> list[int]:
        if not project.repo_owner or not project.repo_name:
            return []

        token = (
            decrypt_value(project.git_provider_token_enc)
            if project.git_provider_token_enc
            else None
        )
        provider = get_git_provider("github", get_http_client(), access_token=token)
        repo_path = f"{project.repo_owner}/{project.repo_name}"

        try:
            issues = await provider.list_issues(repo_path, state="open", limit=100)
        except Exception as exc:
            logger.warning("GitHub poll failed for %s: %s", repo_path, exc)
            return []

        # Filter to ai-task label
        candidates = [i for i in issues if _AI_TASK_LABEL in (i.get("labels") or [])]
        if not candidates:
            return []

        task_ids = [str(i["number"]) for i in candidates]
        already = await existing_task_ids(session, project.project_id, "github", task_ids)

        created: list[int] = []
        for issue in candidates:
            task_id = str(issue["number"])
            if task_id in already:
                continue
            labels = issue.get("labels") or []
            run = create_task_run(
                task_id=task_id,
                project=project,
                title=issue.get("title", ""),
                description=issue.get("body", "") or "",
                task_source="github",
                task_source_meta={
                    "issue_number": issue["number"],
                    "repo_full_name": repo_path,
                    "labels": labels,
                },
                use_claude=_USE_CLAUDE_LABEL in labels,
            )
            session.add(run)
            await session.flush()
            created.append(run.id)
            logger.info("GitHub poll: created run #%d for %s#%s", run.id, repo_path, task_id)
        return created

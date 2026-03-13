# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Posts status comments to task sources (Plane/GitHub/Gitea/GitLab) at phase transitions."""

import logging
from urllib.parse import quote

import httpx

from backend.config import settings

logger = logging.getLogger("agentickode.task_source_updater")


class TaskSourceUpdater:
    """Notifies the originating task source about phase transitions."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def notify(
        self,
        task_source: str,
        task_source_meta: dict,
        phase_name: str,
        status: str,
        run_id: int,
        pr_url: str | None = None,
    ) -> None:
        """Post a comment/update to the task source about a phase transition."""
        try:
            if task_source == "github":
                await self._notify_github(task_source_meta, phase_name, status, run_id, pr_url)
            elif task_source == "plane":
                await self._notify_plane(task_source_meta, phase_name, status, run_id, pr_url)
            elif task_source == "gitea":
                await self._notify_gitea(task_source_meta, phase_name, status, run_id, pr_url)
            elif task_source == "gitlab":
                await self._notify_gitlab(task_source_meta, phase_name, status, run_id, pr_url)
            elif task_source in ("plain", "manual"):
                pass  # No external tracker to notify
            else:
                logger.debug("Unknown task source '%s', skipping notification", task_source)
        except Exception:
            logger.warning("Failed to notify task source '%s'", task_source, exc_info=True)

    async def _notify_github(
        self,
        meta: dict,
        phase_name: str,
        status: str,
        run_id: int,
        pr_url: str | None,
    ) -> None:
        """Post a comment on a GitHub issue."""
        comments_url = meta.get("comments_url")
        token = meta.get("github_token")
        if not comments_url:
            logger.debug("No comments_url in task_source_meta, skipping GitHub notify")
            return

        body = f"**AgenticKode Run #{run_id}** — Phase `{phase_name}` {status}"
        if pr_url:
            body += f"\nPR: {pr_url}"

        headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"

        resp = await self._client.post(
            comments_url, json={"body": body}, headers=headers, timeout=10
        )
        if resp.status_code >= 400:
            logger.warning("GitHub comment failed: %s %s", resp.status_code, resp.text[:200])

    async def _notify_plane(
        self,
        meta: dict,
        phase_name: str,
        status: str,
        run_id: int,
        pr_url: str | None,
    ) -> None:
        """Post an activity/comment on a Plane issue."""
        api_url = meta.get("plane_api_url")
        api_key = meta.get("plane_api_key")
        issue_id = meta.get("issue_id")
        workspace_slug = meta.get("workspace_slug")
        project_id = meta.get("project_id")

        if not all([api_url, issue_id, workspace_slug, project_id]):
            logger.debug("Incomplete Plane metadata, skipping Plane notify")
            return

        comment = f"**AgenticKode Run #{run_id}** — Phase `{phase_name}` {status}"
        if pr_url:
            comment += f"\nPR: {pr_url}"

        url = (
            f"{api_url}/api/v1/workspaces/{workspace_slug}"
            f"/projects/{project_id}/issues/{issue_id}/comments/"
        )
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key

        resp = await self._client.post(
            url, json={"comment_html": f"<p>{comment}</p>"}, headers=headers, timeout=10
        )
        if resp.status_code >= 400:
            logger.warning("Plane comment failed: %s %s", resp.status_code, resp.text[:200])

    async def _notify_gitea(
        self,
        meta: dict,
        phase_name: str,
        status: str,
        run_id: int,
        pr_url: str | None,
    ) -> None:
        """Post a comment on a Gitea issue."""
        repo_full_name = meta.get("repo_full_name", "")
        issue_number = meta.get("issue_number")
        if not repo_full_name or not issue_number:
            logger.debug("Incomplete Gitea metadata, skipping Gitea notify")
            return

        body = f"**AgenticKode Run #{run_id}** — Phase `{phase_name}` {status}"
        if pr_url:
            body += f"\nPR: {pr_url}"

        url = f"{settings.gitea_url}/api/v1/repos/{repo_full_name}/issues/{issue_number}/comments"
        headers: dict[str, str] = {}
        if settings.gitea_token:
            headers["Authorization"] = f"token {settings.gitea_token}"

        resp = await self._client.post(url, json={"body": body}, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.warning("Gitea comment failed: %s %s", resp.status_code, resp.text[:200])

    async def _notify_gitlab(
        self,
        meta: dict,
        phase_name: str,
        status: str,
        run_id: int,
        pr_url: str | None,
    ) -> None:
        """Post a note on a GitLab issue."""
        repo_full_name = meta.get("repo_full_name", "")
        issue_iid = meta.get("issue_iid")
        if not repo_full_name or not issue_iid:
            logger.debug("Incomplete GitLab metadata, skipping GitLab notify")
            return

        body = f"**AgenticKode Run #{run_id}** — Phase `{phase_name}` {status}"
        if pr_url:
            body += f"\nPR: {pr_url}"

        encoded_path = quote(repo_full_name, safe="")
        url = f"{settings.gitlab_api_url}/api/v4/projects/{encoded_path}/issues/{issue_iid}/notes"
        headers: dict[str, str] = {}
        if settings.gitlab_token:
            headers["PRIVATE-TOKEN"] = settings.gitlab_token

        resp = await self._client.post(url, json={"body": body}, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.warning("GitLab note failed: %s %s", resp.status_code, resp.text[:200])

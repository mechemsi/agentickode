# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Polls Plane issues for a project and creates TaskRuns for open ai-task issues.

Credentials are taken from ``project.integration_config``:

- ``plane_api_url`` (or falls back to settings.plane_api_url)
- ``plane_api_key_enc`` or ``plane_api_key`` (prefers encrypted)
- ``workspace_slug`` (required)
- ``plane_project_id`` (required — Plane's project UUID)
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import ProjectConfig
from backend.services.encryption import decrypt_value
from backend.services.http_client import get_http_client
from backend.services.run_factory import create_task_run
from backend.services.task_source_polling._dedupe import existing_task_ids

logger = logging.getLogger("agentickode.polling.plane")

_AI_TASK_LABEL = "ai-task"
_USE_CLAUDE_LABEL = "use-claude"


def _resolve_plane_credentials(project: ProjectConfig) -> tuple[str, str] | None:
    cfg = project.integration_config or {}
    api_url = cfg.get("plane_api_url") or settings.plane_api_url
    api_key_enc = cfg.get("plane_api_key_enc")
    api_key = decrypt_value(api_key_enc) if api_key_enc else cfg.get("plane_api_key")
    api_key = api_key or settings.plane_api_key
    if not api_url or not api_key:
        return None
    return api_url.rstrip("/"), api_key


class PlaneIssuePoller:
    """Pulls open Plane issues labeled ``ai-task`` and dispatches TaskRuns."""

    async def poll(self, project: ProjectConfig, session: AsyncSession) -> list[int]:
        cfg = project.integration_config or {}
        workspace_slug = cfg.get("workspace_slug", "")
        plane_project_id = cfg.get("plane_project_id", "")
        if not workspace_slug or not plane_project_id:
            logger.debug(
                "Skipping Plane poll for %s: missing workspace_slug/plane_project_id",
                project.project_id,
            )
            return []

        creds = _resolve_plane_credentials(project)
        if not creds:
            logger.debug("Skipping Plane poll for %s: no credentials", project.project_id)
            return []
        api_url, api_key = creds

        client = get_http_client()
        url = f"{api_url}/api/v1/workspaces/{workspace_slug}/projects/{plane_project_id}/issues/"
        try:
            resp = await client.get(url, headers={"X-API-Key": api_key}, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Plane poll failed for %s: %s", project.project_id, exc)
            return []

        payload = resp.json()
        issues = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(issues, list):
            return []

        candidates = []
        for issue in issues:
            labels = issue.get("labels", []) or []
            label_names = [
                lbl.get("name", "") if isinstance(lbl, dict) else str(lbl) for lbl in labels
            ]
            state_group = (issue.get("state_detail") or {}).get("group") or issue.get("state_group")
            if _AI_TASK_LABEL not in label_names:
                continue
            if state_group in ("completed", "cancelled"):
                continue
            issue["_label_names"] = label_names
            candidates.append(issue)

        task_ids = [str(i.get("id", "")) for i in candidates if i.get("id")]
        already = await existing_task_ids(session, project.project_id, "plane", task_ids)

        created: list[int] = []
        for issue in candidates:
            task_id = str(issue.get("id", ""))
            if not task_id or task_id in already:
                continue
            labels = issue["_label_names"]
            run = create_task_run(
                task_id=task_id,
                project=project,
                title=issue.get("name", ""),
                description=issue.get("description_html") or issue.get("description", "") or "",
                task_source="plane",
                task_source_meta={
                    "workspace_slug": workspace_slug,
                    "project_id": plane_project_id,
                    "issue_id": task_id,
                    "state_group": (issue.get("state_detail") or {}).get("group", ""),
                    "event": "polled",
                    "labels": labels,
                },
                use_claude=_USE_CLAUDE_LABEL in labels,
            )
            session.add(run)
            await session.flush()
            created.append(run.id)
            logger.info("Plane poll: created run #%d for issue %s", run.id, task_id)
        return created

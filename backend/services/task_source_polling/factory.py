# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Factory mapping task_source strings to their IssuePoller implementation."""

from backend.services.task_source_polling.gitea_poller import GiteaIssuePoller
from backend.services.task_source_polling.github_poller import GitHubIssuePoller
from backend.services.task_source_polling.gitlab_poller import GitLabIssuePoller
from backend.services.task_source_polling.notion_poller import NotionPagePoller
from backend.services.task_source_polling.plane_poller import PlaneIssuePoller
from backend.services.task_source_polling.protocol import IssuePoller

_POLLERS: dict[str, IssuePoller] = {
    "github": GitHubIssuePoller(),
    "gitea": GiteaIssuePoller(),
    "gitlab": GitLabIssuePoller(),
    "plane": PlaneIssuePoller(),
    "notion": NotionPagePoller(),
}


def get_poller(task_source: str) -> IssuePoller | None:
    """Return the IssuePoller for a task_source, or None if polling is unsupported."""
    return _POLLERS.get(task_source)

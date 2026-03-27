# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Linear TaskManager — bidirectional issue sync via GraphQL API."""

import logging

import httpx

logger = logging.getLogger("agentickode.task_management.linear")

_GRAPHQL_URL = "https://api.linear.app/graphql"

# Linear state names vary per team; these are common defaults
_STATUS_STATE_NAME = {
    "in_progress": "In Progress",
    "done": "Done",
    "failed": "Canceled",
}


class LinearTaskManager:
    def __init__(self, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key
        self._headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

    async def _graphql(self, query: str, variables: dict | None = None) -> dict:
        resp = await self._client.post(
            _GRAPHQL_URL,
            headers=self._headers,
            json={"query": query, "variables": variables or {}},
        )
        data = resp.json()
        if "errors" in data:
            logger.warning("Linear GraphQL error: %s", data["errors"])
        return data.get("data", {})

    async def update_status(self, meta: dict, status: str) -> None:
        """Transition Linear issue to a new state."""
        issue_id = meta.get("linear_issue_id") or meta.get("issue_id", "")
        if not issue_id:
            return

        state_name = _STATUS_STATE_NAME.get(status)
        if not state_name:
            return

        # First, find the state ID by name for this issue's team
        state_data = await self._graphql(
            """query($issueId: String!) {
                issue(id: $issueId) {
                    team { states { nodes { id name } } }
                }
            }""",
            {"issueId": issue_id},
        )
        states = (state_data.get("issue") or {}).get("team", {}).get("states", {}).get("nodes", [])
        target_state = next((s for s in states if s["name"] == state_name), None)
        if not target_state:
            logger.warning("Linear state '%s' not found for issue %s", state_name, issue_id)
            return

        await self._graphql(
            """mutation($issueId: String!, $stateId: String!) {
                issueUpdate(id: $issueId, input: { stateId: $stateId }) {
                    issue { id state { name } }
                }
            }""",
            {"issueId": issue_id, "stateId": target_state["id"]},
        )
        logger.info("Linear issue %s → %s", issue_id, state_name)

    async def add_comment(self, meta: dict, body: str) -> None:
        """Post a comment on a Linear issue."""
        issue_id = meta.get("linear_issue_id") or meta.get("issue_id", "")
        if not issue_id:
            return

        await self._graphql(
            """mutation($issueId: String!, $body: String!) {
                commentCreate(input: { issueId: $issueId, body: $body }) {
                    comment { id }
                }
            }""",
            {"issueId": issue_id, "body": body},
        )

    async def create_issue(
        self, project_ref: str, title: str, body: str, labels: list[str] | None = None
    ) -> dict:
        """Create a Linear issue. project_ref = team key (e.g. 'ENG')."""
        data = await self._graphql(
            """mutation($teamKey: String!, $title: String!, $description: String!) {
                issueCreate(input: { teamId: $teamKey, title: $title, description: $description }) {
                    issue { id url identifier }
                }
            }""",
            {"teamKey": project_ref, "title": title, "description": body},
        )
        issue = (data.get("issueCreate") or {}).get("issue", {})
        return {"id": issue.get("id", ""), "url": issue.get("url", "")}

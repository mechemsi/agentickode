# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for the project issues API endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture(autouse=True)
def mock_get_default_branch():
    """Patch get_default_branch so tests don't hit real provider APIs."""
    with (
        patch(
            "backend.api.projects.get_default_branch",
            new_callable=AsyncMock,
            return_value="main",
        ),
        patch(
            "backend.api.projects.get_default_branch_via_ssh",
            new_callable=AsyncMock,
            return_value="main",
        ),
    ):
        yield


class TestListProjectIssues:
    """Tests for GET /projects/{project_id:path}/issues."""

    async def test_returns_issues_for_valid_project(self, client):
        """Creates a project, mocks list_issues, and verifies response."""
        project = {
            "project_id": "proj-issues-1",
            "project_slug": "issue-test",
            "repo_owner": "org",
            "repo_name": "repo",
            "default_branch": "main",
            "task_source": "github",
            "git_provider": "github",
        }
        resp = await client.post("/api/projects", json=project)
        assert resp.status_code == 201

        mock_issues = [
            {
                "number": 5,
                "title": "Fix login",
                "body": "Login is broken",
                "labels": ["bug"],
                "url": "https://github.com/org/repo/issues/5",
                "state": "open",
            },
        ]

        with patch("backend.api.project_issues.get_git_provider") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.list_issues.return_value = mock_issues
            mock_factory.return_value = mock_provider

            resp = await client.get("/api/projects/proj-issues-1/issues")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["number"] == 5
        assert data[0]["title"] == "Fix login"
        assert data[0]["body"] == "Login is broken"
        assert data[0]["labels"] == ["bug"]

    async def test_project_id_with_slash(self, client):
        """Project IDs like 'owner/repo' should resolve correctly."""
        project = {
            "project_id": "myorg/myrepo",
            "project_slug": "myrepo",
            "repo_owner": "myorg",
            "repo_name": "myrepo",
            "default_branch": "main",
            "task_source": "gitea",
            "git_provider": "gitea",
        }
        resp = await client.post("/api/projects", json=project)
        assert resp.status_code == 201

        mock_issues = [
            {
                "number": 1,
                "title": "Test issue",
                "body": "",
                "labels": [],
                "url": "",
                "state": "open",
            }
        ]

        with patch("backend.api.project_issues.get_git_provider") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.list_issues.return_value = mock_issues
            mock_factory.return_value = mock_provider

            resp = await client.get("/api/projects/myorg/myrepo/issues")

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["title"] == "Test issue"

    async def test_returns_empty_for_plain_project(self, client):
        """Plain projects have no git issues — should return []."""
        project = {
            "project_id": "proj-plain-1",
            "project_slug": "plain-proj",
            "repo_owner": "org",
            "repo_name": "repo",
            "default_branch": "main",
            "task_source": "plain",
            "git_provider": "gitea",
        }
        resp = await client.post("/api/projects", json=project)
        assert resp.status_code == 201

        resp = await client.get("/api/projects/proj-plain-1/issues")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_404_for_missing_project(self, client):
        resp = await client.get("/api/projects/nonexistent/issues")
        assert resp.status_code == 404

    async def test_returns_502_on_auth_failure(self, client):
        """Provider returns 401/403 → endpoint returns 502."""
        project = {
            "project_id": "proj-auth-fail",
            "project_slug": "auth-fail",
            "repo_owner": "org",
            "repo_name": "repo",
            "default_branch": "main",
            "task_source": "github",
            "git_provider": "github",
        }
        resp = await client.post("/api/projects", json=project)
        assert resp.status_code == 201

        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("backend.api.project_issues.get_git_provider") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.list_issues.side_effect = httpx.HTTPStatusError(
                "403 Forbidden", request=MagicMock(), response=mock_response
            )
            mock_factory.return_value = mock_provider

            resp = await client.get("/api/projects/proj-auth-fail/issues")

        assert resp.status_code == 502
        assert "auth failed" in resp.json()["detail"].lower()

    async def test_returns_502_on_network_error(self, client):
        """Provider unreachable → endpoint returns 502."""
        project = {
            "project_id": "proj-net-fail",
            "project_slug": "net-fail",
            "repo_owner": "org",
            "repo_name": "repo",
            "default_branch": "main",
            "task_source": "gitea",
            "git_provider": "gitea",
        }
        resp = await client.post("/api/projects", json=project)
        assert resp.status_code == 201

        with patch("backend.api.project_issues.get_git_provider") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.list_issues.side_effect = httpx.ConnectError("Connection refused")
            mock_factory.return_value = mock_provider

            resp = await client.get("/api/projects/proj-net-fail/issues")

        assert resp.status_code == 502
        assert "cannot reach" in resp.json()["detail"].lower()

    async def test_fetches_via_ssh_when_workspace_server_linked(self, client, db_session):
        """When project has workspace_server_id, issues are fetched via SSH."""
        from backend.models import WorkspaceServer
        from backend.models.projects import ProjectConfig

        server = WorkspaceServer(
            name="test-ws",
            hostname="10.0.0.1",
            port=22,
            username="root",
            workspace_root="/workspaces",
            status="online",
        )
        db_session.add(server)
        await db_session.flush()

        proj = ProjectConfig(
            project_id="proj-ssh-issues",
            project_slug="ssh-proj",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
            task_source="gitea",
            git_provider="gitea",
            workspace_server_id=server.id,
        )
        db_session.add(proj)
        await db_session.commit()

        ssh_json = '[{"number":1,"title":"SSH issue","body":"from ssh","labels":[],"html_url":"","state":"open"}]'

        with patch("backend.api.project_issues.SSHService") as mock_ssh_cls:
            mock_ssh = MagicMock()
            mock_ssh.run_command = AsyncMock(return_value=(ssh_json, "", 0))
            mock_ssh_cls.for_server.return_value = mock_ssh

            resp = await client.get("/api/projects/proj-ssh-issues/issues")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "SSH issue"
        mock_ssh.run_command.assert_called_once()

    async def test_falls_back_to_direct_on_ssh_failure(self, client, db_session):
        """SSH failure falls back to direct HTTP."""
        from backend.models import WorkspaceServer
        from backend.models.projects import ProjectConfig

        server = WorkspaceServer(
            name="test-ws-2",
            hostname="10.0.0.2",
            port=22,
            username="root",
            workspace_root="/workspaces",
            status="online",
        )
        db_session.add(server)
        await db_session.flush()

        proj = ProjectConfig(
            project_id="proj-ssh-fallback",
            project_slug="fallback-proj",
            repo_owner="org",
            repo_name="repo",
            default_branch="main",
            task_source="gitea",
            git_provider="gitea",
            workspace_server_id=server.id,
        )
        db_session.add(proj)
        await db_session.commit()

        fallback_issues = [
            {
                "number": 2,
                "title": "Fallback issue",
                "body": "",
                "labels": [],
                "url": "",
                "state": "open",
            }
        ]

        with (
            patch("backend.api.project_issues.SSHService") as mock_ssh_cls,
            patch("backend.api.project_issues.get_git_provider") as mock_factory,
        ):
            mock_ssh = MagicMock()
            mock_ssh.run_command = AsyncMock(side_effect=RuntimeError("SSH failed"))
            mock_ssh_cls.for_server.return_value = mock_ssh

            mock_provider = AsyncMock()
            mock_provider.list_issues.return_value = fallback_issues
            mock_factory.return_value = mock_provider

            resp = await client.get("/api/projects/proj-ssh-fallback/issues")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Fallback issue"
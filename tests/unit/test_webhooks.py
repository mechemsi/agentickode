# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for webhook helpers."""

from unittest.mock import MagicMock

from backend.api.webhooks import _create_task_run, _resolve_workspace_path


class TestResolveWorkspacePath:
    def _make_project(self, workspace_config=None, project_id="proj-1", workspace_path=None):
        p = MagicMock()
        p.project_id = project_id
        p.workspace_config = workspace_config
        p.workspace_path = workspace_path
        return p

    def test_existing_workspace_type(self):
        project = self._make_project({"workspace_type": "existing"})
        assert _resolve_workspace_path(project, "task-123") == "/workspaces/proj-1"

    def test_cluster_workspace_type(self):
        project = self._make_project({"workspace_type": "cluster"})
        assert _resolve_workspace_path(project, "task-123") == "/workspaces/task-123"

    def test_default_without_config(self):
        project = self._make_project(None)
        assert _resolve_workspace_path(project, "task-123") == "/workspaces/proj-1"

    def test_default_with_empty_config(self):
        project = self._make_project({})
        assert _resolve_workspace_path(project, "task-123") == "/workspaces/proj-1"

    def test_uses_discovered_workspace_path(self):
        project = self._make_project(None, workspace_path="/home/workspace/linker")
        assert _resolve_workspace_path(project, "task-123") == "/home/workspace/linker"

    def test_discovered_path_with_existing_type(self):
        project = self._make_project(
            {"workspace_type": "existing"}, workspace_path="/srv/repos/myproject"
        )
        assert _resolve_workspace_path(project, "task-123") == "/srv/repos/myproject"

    def test_cluster_overrides_discovered_path(self):
        project = self._make_project(
            {"workspace_type": "cluster"}, workspace_path="/home/workspace/linker"
        )
        assert _resolve_workspace_path(project, "task-123") == "/workspaces/task-123"


class TestCreateTaskRun:
    def _make_project(self):
        p = MagicMock()
        p.project_id = "proj-1"
        p.repo_owner = "org"
        p.repo_name = "repo"
        p.default_branch = "main"
        p.git_provider = "gitea"
        p.workspace_config = None
        p.workspace_path = None
        return p

    def test_creates_run_with_correct_fields(self):
        project = self._make_project()
        run = _create_task_run(
            task_id="TASK-42",
            project=project,
            title="Fix bug",
            description="Fix the login bug",
            task_source="plane",
            task_source_meta={"event": "created"},
            use_claude=False,
        )
        assert run.task_id == "TASK-42"
        assert run.project_id == "proj-1"
        assert run.branch_name == "feature/ai-TASK-42"
        assert run.workspace_path == "/workspaces/proj-1"
        assert run.repo_owner == "org"
        assert run.git_provider == "gitea"
        assert run.use_claude_api is False

    def test_use_claude_flag(self):
        project = self._make_project()
        run = _create_task_run(
            task_id="TASK-1",
            project=project,
            title="t",
            description="d",
            task_source="github",
            task_source_meta={},
            use_claude=True,
        )
        assert run.use_claude_api is True
        assert run.task_source == "github"
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Unit tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError

from backend.schemas import (
    ProjectConfigCreate,
    ProjectConfigUpdate,
    RejectRequest,
    TaskRunOut,
)


class TestProjectConfigCreate:
    def test_minimal_valid(self):
        cfg = ProjectConfigCreate(
            project_id="proj-1",
            project_slug="my-project",
            repo_owner="org",
            repo_name="repo",
        )
        assert cfg.project_id == "proj-1"
        assert cfg.default_branch == "main"
        assert cfg.task_source == "plane"
        assert cfg.git_provider == "gitea"

    def test_full_valid(self):
        cfg = ProjectConfigCreate(
            project_id="proj-2",
            project_slug="full-project",
            repo_owner="org",
            repo_name="repo",
            default_branch="develop",
            task_source="github",
            git_provider="github",
            workspace_config={"workspace_type": "cluster"},
            ai_config={"model": "gpt-4"},
        )
        assert cfg.default_branch == "develop"
        assert cfg.workspace_config == {"workspace_type": "cluster"}

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ProjectConfigCreate(project_id="proj-1")


class TestProjectConfigUpdate:
    def test_all_optional(self):
        update = ProjectConfigUpdate()
        assert update.project_slug is None
        assert update.repo_owner is None

    def test_partial_update(self):
        update = ProjectConfigUpdate(repo_owner="new-org")
        dump = update.model_dump(exclude_unset=True)
        assert dump == {"repo_owner": "new-org"}


class TestRejectRequest:
    def test_default_empty_reason(self):
        req = RejectRequest()
        assert req.reason == ""

    def test_with_reason(self):
        req = RejectRequest(reason="code quality issues")
        assert req.reason == "code quality issues"


class TestTaskRunOut:
    def test_from_attributes(self):
        """Ensure from_attributes is set for ORM compatibility."""
        assert TaskRunOut.model_config.get("from_attributes") is True
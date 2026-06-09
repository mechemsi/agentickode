# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for PR-review webhook + CI trigger endpoints (webhooks_pr.py)."""

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.config import settings
from backend.models import ProjectConfig, TaskRun, WorkflowTemplate
from backend.seed.workflow_templates import seed_workflow_templates


@pytest.fixture()
async def github_project(db_session):
    p = ProjectConfig(
        project_id="gh-proj",
        project_slug="gh-proj",
        repo_owner="myorg",
        repo_name="myrepo",
        default_branch="main",
        task_source="github",
        git_provider="github",
        workspace_path="/workspaces/myrepo",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.fixture()
async def pr_review_template(db_session):
    await seed_workflow_templates(db_session)
    result = await db_session.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.name == "pr-review")
    )
    return result.scalar_one()


def _pr_payload(
    action="opened",
    labels=None,
    pr_number=11,
    title="Add feature",
    body="PR body",
    head_ref="feature/x",
    repo_full_name="myorg/myrepo",
):
    if labels is None:
        labels = [{"name": "ai-review"}]
    return {
        "action": action,
        "pull_request": {
            "number": pr_number,
            "title": title,
            "body": body,
            "html_url": f"https://github.com/{repo_full_name}/pull/{pr_number}",
            "head": {"ref": head_ref},
            "labels": labels,
        },
        "repository": {"full_name": repo_full_name},
    }


class TestGithubPrWebhook:
    async def test_ai_review_label_creates_review_run(
        self, client: AsyncClient, github_project, pr_review_template, db_session
    ):
        resp = await client.post("/api/webhooks/github-pr", json=_pr_payload())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"

        run = await db_session.get(TaskRun, data["run_id"])
        assert run is not None
        assert run.workflow_template_id == pr_review_template.id
        assert run.task_id == "pr-11"
        assert run.task_source_meta["review_mode"] == "comment"
        assert run.task_source_meta["pr_number"] == 11
        assert run.task_source_meta["pr_head_branch"] == "feature/x"
        assert run.max_retries == 0

    async def test_without_ai_review_label_is_ignored(
        self, client: AsyncClient, github_project, pr_review_template, db_session
    ):
        payload = _pr_payload(labels=[{"name": "bug"}])
        resp = await client.post("/api/webhooks/github-pr", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

        runs = (await db_session.execute(select(TaskRun))).scalars().all()
        assert runs == []

    async def test_labeled_action_triggers_review(
        self, client: AsyncClient, github_project, pr_review_template
    ):
        resp = await client.post("/api/webhooks/github-pr", json=_pr_payload(action="labeled"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_closed_action_is_ignored(
        self, client: AsyncClient, github_project, pr_review_template
    ):
        resp = await client.post("/api/webhooks/github-pr", json=_pr_payload(action="closed"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    async def test_unknown_project_is_ignored(
        self, client: AsyncClient, github_project, pr_review_template
    ):
        payload = _pr_payload(repo_full_name="someoneelse/repo")
        resp = await client.post("/api/webhooks/github-pr", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    async def test_malformed_json_returns_400(
        self, client: AsyncClient, github_project, pr_review_template
    ):
        resp = await client.post(
            "/api/webhooks/github-pr",
            content=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_duplicate_inflight_review_is_skipped(
        self, client: AsyncClient, github_project, pr_review_template, db_session, make_task_run
    ):
        # A review for PR #11 is already running.
        existing = make_task_run(
            project_id="gh-proj",
            task_id="pr-11",
            task_source="github",
            status="running",
            task_source_meta={"review_mode": "comment", "pr_number": 11},
        )
        db_session.add(existing)
        await db_session.commit()

        resp = await client.post("/api/webhooks/github-pr", json=_pr_payload(pr_number=11))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

        runs = (
            (await db_session.execute(select(TaskRun).where(TaskRun.task_id == "pr-11")))
            .scalars()
            .all()
        )
        assert len(runs) == 1  # no duplicate created


class TestGithubPrWebhookHmac:
    @pytest.fixture(autouse=True)
    def _set_secret(self, monkeypatch):
        monkeypatch.setattr(settings, "github_webhook_secret", "topsecret")

    async def test_valid_signature_accepted(
        self, client: AsyncClient, github_project, pr_review_template
    ):
        raw = json.dumps(_pr_payload()).encode()
        sig = "sha256=" + hmac.new(b"topsecret", raw, hashlib.sha256).hexdigest()
        resp = await client.post(
            "/api/webhooks/github-pr",
            content=raw,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_bad_signature_rejected(
        self, client: AsyncClient, github_project, pr_review_template
    ):
        raw = json.dumps(_pr_payload()).encode()
        resp = await client.post(
            "/api/webhooks/github-pr",
            content=raw,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=bad"},
        )
        assert resp.status_code == 401


class TestCiPrReviewEndpoint:
    async def test_ci_trigger_creates_review_run(
        self, client: AsyncClient, github_project, pr_review_template, db_session
    ):
        resp = await client.post(
            "/api/webhooks/pr-review",
            json={"provider": "github", "repo": "myorg/myrepo", "pr_number": 22},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"

        run = await db_session.get(TaskRun, data["run_id"])
        assert run is not None
        assert run.workflow_template_id == pr_review_template.id
        assert run.task_id == "pr-22"
        assert run.task_source_meta["pr_number"] == 22
        assert run.task_source_meta["review_mode"] == "comment"
        assert run.max_retries == 0

    async def test_ci_trigger_binds_flow_prompt_when_enabled(
        self, client: AsyncClient, github_project, pr_review_template, db_session, monkeypatch
    ):
        # Regression (ADR-009 live validation): the CI endpoint must bind the
        # pr_review flow prompt when the flag is on, else Phase 3's default
        # mis-routes the PR review to the implement flow.
        from backend.config import settings
        from backend.models import FlowPrompt
        from backend.repositories.flow_prompt_repo import FlowPromptRepository

        monkeypatch.setattr(settings, "flow_prompts_enabled", True)
        flow = await FlowPromptRepository(db_session).create(
            FlowPrompt(name="pr-review", flow_type="pr_review", prompt="x", agent_mode="generate")
        )
        await db_session.commit()

        resp = await client.post(
            "/api/webhooks/pr-review",
            json={"provider": "github", "repo": "myorg/myrepo", "pr_number": 24},
        )
        assert resp.status_code == 200
        run = await db_session.get(TaskRun, resp.json()["run_id"])
        assert run is not None
        assert run.flow_prompt_id == flow.id

    async def test_ci_trigger_rejects_nonpositive_pr_number(
        self, client: AsyncClient, github_project, pr_review_template
    ):
        resp = await client.post(
            "/api/webhooks/pr-review",
            json={"provider": "github", "repo": "myorg/myrepo", "pr_number": 0},
        )
        assert resp.status_code == 422

    async def test_ci_trigger_unknown_project_404(
        self, client: AsyncClient, github_project, pr_review_template
    ):
        resp = await client.post(
            "/api/webhooks/pr-review",
            json={"provider": "github", "repo": "nope/missing", "pr_number": 1},
        )
        assert resp.status_code == 404

    async def test_ci_trigger_requires_token_when_secret_set(
        self, client: AsyncClient, github_project, pr_review_template, monkeypatch
    ):
        monkeypatch.setattr(settings, "ci_trigger_secret", "ci-secret")
        # Missing token → 401
        resp = await client.post(
            "/api/webhooks/pr-review",
            json={"provider": "github", "repo": "myorg/myrepo", "pr_number": 5},
        )
        assert resp.status_code == 401
        # Wrong token → 401
        resp = await client.post(
            "/api/webhooks/pr-review",
            json={"provider": "github", "repo": "myorg/myrepo", "pr_number": 5},
            headers={"X-CI-Token": "wrong"},
        )
        assert resp.status_code == 401

    async def test_ci_trigger_accepts_valid_token(
        self, client: AsyncClient, github_project, pr_review_template, monkeypatch
    ):
        monkeypatch.setattr(settings, "ci_trigger_secret", "ci-secret")
        resp = await client.post(
            "/api/webhooks/pr-review",
            json={"provider": "github", "repo": "myorg/myrepo", "pr_number": 5},
            headers={"X-CI-Token": "ci-secret"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_ci_trigger_without_template_503(self, client: AsyncClient, github_project):
        # No pr_review_template fixture → template absent → cannot review.
        resp = await client.post(
            "/api/webhooks/pr-review",
            json={"provider": "github", "repo": "myorg/myrepo", "pr_number": 1},
        )
        assert resp.status_code == 503

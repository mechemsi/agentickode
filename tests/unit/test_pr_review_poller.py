# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for the PR-review poller (webhook-less polling for ai-review PRs)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.models import FlowPrompt, ProjectConfig, TaskRun
from backend.seed.flow_prompts import seed_flow_prompts
from backend.services.task_source_polling.pr_review_poller import poll_pr_reviews


@pytest.fixture()
async def gitea_project(db_session):
    p = ProjectConfig(
        project_id="poll-proj",
        project_slug="poll",
        repo_owner="o",
        repo_name="r",
        default_branch="main",
        task_source="gitea",
        git_provider="gitea",
        poll_enabled=True,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.fixture()
async def pr_template(db_session):
    await seed_flow_prompts(db_session)
    result = await db_session.execute(select(FlowPrompt).where(FlowPrompt.flow_type == "pr_review"))
    return result.scalars().first()


def _pr(number=11, labels=("ai-review",), head_sha="sha1"):
    return {
        "number": number,
        "title": f"PR {number}",
        "body": "b",
        "labels": list(labels),
        "head_ref": "feat",
        "head_sha": head_sha,
        "html_url": f"https://gitea.test/o/r/pulls/{number}",
        "state": "open",
    }


def _provider_returning(prs):
    provider = MagicMock()
    provider.list_pull_requests = AsyncMock(return_value=prs)
    return provider


class TestPrReviewPoller:
    async def test_creates_review_run_for_ai_review_pr(
        self, db_session, gitea_project, pr_template
    ):
        provider = _provider_returning([_pr()])
        with (
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_git_provider",
                new=MagicMock(return_value=provider),
            ),
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_http_client",
                new=MagicMock(),
            ),
        ):
            created = await poll_pr_reviews(gitea_project, db_session)
        assert len(created) == 1

        run = await db_session.get(TaskRun, created[0])
        assert run.task_id == "pr-11"
        assert run.flow_prompt_id == pr_template.id
        assert run.task_source_meta["review_mode"] == "comment"
        assert run.task_source_meta["pr_head_sha"] == "sha1"
        assert run.max_retries == 0

    async def test_skips_pr_without_review_labels(self, db_session, gitea_project, pr_template):
        provider = _provider_returning([_pr(labels=("bug",))])
        with (
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_git_provider",
                new=MagicMock(return_value=provider),
            ),
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_http_client",
                new=MagicMock(),
            ),
        ):
            created = await poll_pr_reviews(gitea_project, db_session)
        assert created == []

    async def test_dedupes_same_head_sha(self, db_session, gitea_project, pr_template):
        provider = _provider_returning([_pr(head_sha="sha1")])
        with (
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_git_provider",
                new=MagicMock(return_value=provider),
            ),
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_http_client",
                new=MagicMock(),
            ),
        ):
            first = await poll_pr_reviews(gitea_project, db_session)
            await db_session.commit()
            # mark the run completed so it's no longer "in-flight"
            run = await db_session.get(TaskRun, first[0])
            run.status = "completed"
            await db_session.commit()
            second = await poll_pr_reviews(gitea_project, db_session)
        assert len(first) == 1
        assert second == []  # same SHA already reviewed

    async def test_no_auto_rereview_by_default(self, db_session, gitea_project, pr_template):
        """Without the per-project opt-in, a reviewed PR is NOT re-reviewed on new commits."""
        with (
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_http_client",
                new=MagicMock(),
            ),
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_git_provider",
                new=MagicMock(return_value=_provider_returning([_pr(head_sha="sha1")])),
            ),
        ):
            first = await poll_pr_reviews(gitea_project, db_session)
            await db_session.commit()
            run = await db_session.get(TaskRun, first[0])
            run.status = "completed"
            await db_session.commit()

        # New commit + already-reviewed label, but project did NOT opt in → no re-review.
        with (
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_http_client",
                new=MagicMock(),
            ),
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_git_provider",
                new=MagicMock(
                    return_value=_provider_returning(
                        [_pr(labels=("ai-reviewed",), head_sha="sha2")]
                    )
                ),
            ),
        ):
            second = await poll_pr_reviews(gitea_project, db_session)
        assert len(first) == 1
        assert second == []

    async def test_rereviews_on_new_head_sha(self, db_session, gitea_project, pr_template):
        # Project opts in to automatic re-review on new commits.
        gitea_project.integration_config = {"pr_review_rereview_on_push": True}
        await db_session.commit()
        with (
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_http_client",
                new=MagicMock(),
            ),
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_git_provider",
                new=MagicMock(return_value=_provider_returning([_pr(head_sha="sha1")])),
            ),
        ):
            first = await poll_pr_reviews(gitea_project, db_session)
            await db_session.commit()
            run = await db_session.get(TaskRun, first[0])
            run.status = "completed"
            await db_session.commit()

        # New commit pushed → head SHA changes → re-review (label now ai-reviewed)
        with (
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_http_client",
                new=MagicMock(),
            ),
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_git_provider",
                new=MagicMock(
                    return_value=_provider_returning(
                        [_pr(labels=("ai-reviewed",), head_sha="sha2")]
                    )
                ),
            ),
        ):
            second = await poll_pr_reviews(gitea_project, db_session)
        assert len(second) == 1
        run2 = await db_session.get(TaskRun, second[0])
        assert run2.task_source_meta["pr_head_sha"] == "sha2"

    async def test_uses_project_scoped_git_connection_token(
        self, db_session, gitea_project, pr_template
    ):
        """The poller must resolve the project's git_connections token (not just legacy)."""
        from backend.models import GitConnection
        from backend.services.encryption import encrypt_value

        db_session.add(
            GitConnection(
                name="proj-gitea",
                provider="gitea",
                scope="project",
                project_id="poll-proj",
                token_enc=encrypt_value("conn-token"),
            )
        )
        await db_session.commit()

        provider = _provider_returning([])
        get_provider = MagicMock(return_value=provider)
        with (
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_git_provider",
                new=get_provider,
            ),
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_http_client",
                new=MagicMock(),
            ),
        ):
            await poll_pr_reviews(gitea_project, db_session)

        assert get_provider.call_args.kwargs["access_token"] == "conn-token"

    async def test_scheduler_runs_pr_poll_even_without_issue_poller(
        self, db_session, gitea_project
    ):
        """_poll_project runs the PR poll for git projects and still advances next_poll_at."""
        from backend.worker.issue_poller_scheduler import IssuePollerScheduler

        sched = IssuePollerScheduler(MagicMock())
        with (
            patch(
                "backend.worker.issue_poller_scheduler.get_poller",
                new=MagicMock(return_value=None),
            ),
            patch(
                "backend.worker.issue_poller_scheduler.poll_pr_reviews",
                new=AsyncMock(return_value=[1, 2]),
            ) as mock_poll,
        ):
            await sched._poll_project(db_session, gitea_project, datetime.now(UTC))

        mock_poll.assert_awaited_once()
        assert gitea_project.next_poll_at is not None

    async def test_does_not_double_start_inflight(self, db_session, gitea_project, pr_template):
        provider = _provider_returning([_pr(head_sha="sha1")])
        with (
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_git_provider",
                new=MagicMock(return_value=provider),
            ),
            patch(
                "backend.services.task_source_polling.pr_review_poller.get_http_client",
                new=MagicMock(),
            ),
        ):
            first = await poll_pr_reviews(gitea_project, db_session)
            await db_session.commit()
            # run still pending/running → next poll must not start another
            second = await poll_pr_reviews(gitea_project, db_session)
        assert len(first) == 1
        assert second == []

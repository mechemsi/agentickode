# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for WebhookCallbackService."""

from unittest.mock import AsyncMock

import httpx
import pytest

from backend.models import ProjectConfig, WebhookCallback
from backend.services.webhook_callback_service import WebhookCallbackService


@pytest.fixture()
def mock_client():
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture()
def service(mock_client):
    return WebhookCallbackService(mock_client)


class TestWebhookCallbackService:
    async def test_fire_sends_to_matching_callbacks(
        self, db_session, service, mock_client, make_task_run
    ):
        project = ProjectConfig(
            project_id="proj-wh1", project_slug="wh1", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-wh1")
        db_session.add(run)
        await db_session.commit()

        cb = WebhookCallback(
            run_id=run.id,
            url="https://hook.example.com/callback",
            events=["phase_completed"],
            active=True,
        )
        db_session.add(cb)
        await db_session.commit()

        mock_client.post.return_value = httpx.Response(200)

        await service.fire(db_session, run.id, "phase_completed", {"phase": "coding"})

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://hook.example.com/callback"
        body = call_args[1]["json"]
        assert body["event"] == "phase_completed"
        assert body["run_id"] == run.id
        assert body["phase"] == "coding"

    async def test_fire_skips_non_matching_events(
        self, db_session, service, mock_client, make_task_run
    ):
        project = ProjectConfig(
            project_id="proj-wh2", project_slug="wh2", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-wh2")
        db_session.add(run)
        await db_session.commit()

        cb = WebhookCallback(
            run_id=run.id,
            url="https://hook.example.com/callback",
            events=["run_completed"],
            active=True,
        )
        db_session.add(cb)
        await db_session.commit()

        await service.fire(db_session, run.id, "phase_completed", {"phase": "coding"})

        mock_client.post.assert_not_called()

    async def test_fire_sends_to_all_event_callbacks(
        self, db_session, service, mock_client, make_task_run
    ):
        """Callbacks with empty events list receive all events."""
        project = ProjectConfig(
            project_id="proj-wh3", project_slug="wh3", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-wh3")
        db_session.add(run)
        await db_session.commit()

        cb = WebhookCallback(
            run_id=run.id, url="https://hook.example.com/all", events=[], active=True
        )
        db_session.add(cb)
        await db_session.commit()

        mock_client.post.return_value = httpx.Response(200)

        await service.fire(db_session, run.id, "phase_failed", {"phase": "coding"})

        mock_client.post.assert_called_once()

    async def test_fire_skips_inactive_callbacks(
        self, db_session, service, mock_client, make_task_run
    ):
        project = ProjectConfig(
            project_id="proj-wh4", project_slug="wh4", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-wh4")
        db_session.add(run)
        await db_session.commit()

        cb = WebhookCallback(
            run_id=run.id, url="https://hook.example.com/inactive", events=[], active=False
        )
        db_session.add(cb)
        await db_session.commit()

        await service.fire(db_session, run.id, "phase_completed", {"phase": "coding"})

        mock_client.post.assert_not_called()

    async def test_fire_handles_http_error_gracefully(
        self, db_session, service, mock_client, make_task_run
    ):
        project = ProjectConfig(
            project_id="proj-wh5", project_slug="wh5", repo_owner="o", repo_name="r"
        )
        db_session.add(project)
        run = make_task_run(project_id="proj-wh5")
        db_session.add(run)
        await db_session.commit()

        cb = WebhookCallback(
            run_id=run.id, url="https://hook.example.com/error", events=[], active=True
        )
        db_session.add(cb)
        await db_session.commit()

        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        # Should not raise
        await service.fire(db_session, run.id, "phase_completed", {"phase": "coding"})
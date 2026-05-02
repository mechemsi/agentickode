# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for NotionTaskManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.task_management.notion_manager import NotionTaskManager


@pytest.fixture()
def client():
    c = MagicMock()
    c.patch = AsyncMock(return_value=MagicMock(status_code=200, text=""))
    c.post = AsyncMock(return_value=MagicMock(status_code=200, text="", json=lambda: {"id": "p1"}))
    return c


class TestUpdateStatus:
    async def test_maps_internal_status_to_notion_select_name(self, client):
        mgr = NotionTaskManager(client, api_key="secret")
        await mgr.update_status({"page_id": "abc"}, "in_progress")

        client.patch.assert_called_once()
        url = client.patch.call_args.args[0]
        payload = client.patch.call_args.kwargs["json"]
        headers = client.patch.call_args.kwargs["headers"]
        assert url.endswith("/pages/abc")
        assert payload["properties"]["Status"]["select"]["name"] == "In Progress"
        assert headers["Authorization"] == "Bearer secret"
        assert headers["Notion-Version"]

    async def test_honours_custom_status_property_and_map(self, client):
        mgr = NotionTaskManager(
            client,
            api_key="secret",
            status_map={"done": "Shipped"},
            status_property="Workflow State",
        )
        await mgr.update_status({"page_id": "abc", "status_property": "Workflow State"}, "done")
        payload = client.patch.call_args.kwargs["json"]
        assert payload["properties"]["Workflow State"]["select"]["name"] == "Shipped"

    async def test_ignores_unmapped_status(self, client):
        mgr = NotionTaskManager(client, api_key="secret")
        await mgr.update_status({"page_id": "abc"}, "unknown")
        client.patch.assert_not_called()

    async def test_ignores_missing_page_id(self, client):
        mgr = NotionTaskManager(client, api_key="secret")
        await mgr.update_status({}, "in_progress")
        client.patch.assert_not_called()


class TestAddComment:
    async def test_posts_comment_to_notion(self, client):
        mgr = NotionTaskManager(client, api_key="secret")
        await mgr.add_comment({"page_id": "abc"}, "hello")
        payload = client.post.call_args.kwargs["json"]
        assert payload["parent"]["page_id"] == "abc"
        assert payload["rich_text"][0]["text"]["content"] == "hello"


class TestCreateIssue:
    async def test_creates_page_in_database(self, client):
        client.post = AsyncMock(
            return_value=MagicMock(
                status_code=200,
                text="",
                json=lambda: {"id": "new-page", "url": "https://notion.so/new-page"},
            )
        )
        mgr = NotionTaskManager(client, api_key="secret")
        out = await mgr.create_issue("db-123", "title", "body", labels=["ai-task"])
        payload = client.post.call_args.kwargs["json"]
        assert payload["parent"]["database_id"] == "db-123"
        assert payload["properties"]["Name"]["title"][0]["text"]["content"] == "title"
        assert payload["properties"]["Tags"]["multi_select"] == [{"name": "ai-task"}]
        assert out == {"id": "new-page", "url": "https://notion.so/new-page"}

    async def test_returns_empty_on_failure(self, client):
        client.post = AsyncMock(return_value=MagicMock(status_code=400, text="bad", json=dict))
        mgr = NotionTaskManager(client, api_key="secret")
        out = await mgr.create_issue("db-123", "title", "body")
        assert out == {"id": "", "url": ""}


class TestFactoryNotion:
    def _project(self, integration_config: dict | None) -> MagicMock:
        p = MagicMock()
        p.integration_config = integration_config
        return p

    def test_get_task_manager_returns_notion_with_plaintext_key(self):
        from backend.services.task_management import factory as factory_mod

        client = MagicMock()
        project = self._project({"notion_api_key": "plain-secret"})
        manager = factory_mod.get_task_manager("notion", client, project=project)
        assert isinstance(manager, factory_mod.NotionTaskManager)

    def test_get_task_manager_returns_notion_with_encrypted_key(self):
        from backend.services.encryption import encrypt_value
        from backend.services.task_management import factory as factory_mod

        client = MagicMock()
        project = self._project({"notion_api_key_enc": encrypt_value("real-secret")})
        manager = factory_mod.get_task_manager("notion", client, project=project)
        assert isinstance(manager, factory_mod.NotionTaskManager)

    def test_get_task_manager_falls_back_to_noop_without_key(self):
        from backend.services.task_management import factory as factory_mod

        client = MagicMock()
        project = self._project({})
        manager = factory_mod.get_task_manager("notion", client, project=project)
        # No API key → falls back to NoOp, not NotionTaskManager
        assert not isinstance(manager, factory_mod.NotionTaskManager)

    def test_get_task_manager_notion_without_project_returns_noop(self):
        from backend.services.task_management import factory as factory_mod

        client = MagicMock()
        manager = factory_mod.get_task_manager("notion", client, project=None)
        assert not isinstance(manager, factory_mod.NotionTaskManager)

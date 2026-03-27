# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from unittest.mock import MagicMock

from backend.services.task_management.factory import NoOpTaskManager, get_task_manager


class TestTaskManagerFactory:
    def test_unknown_source_returns_noop(self):
        client = MagicMock()
        manager = get_task_manager("unknown", client)
        assert isinstance(manager, NoOpTaskManager)

    def test_manual_source_returns_noop(self):
        client = MagicMock()
        manager = get_task_manager("manual", client)
        assert isinstance(manager, NoOpTaskManager)


class TestGitHubStatusLabels:
    def test_status_label_mapping(self):
        from backend.services.task_management.github_manager import _STATUS_LABELS

        assert "in_progress" in _STATUS_LABELS
        assert "done" in _STATUS_LABELS
        assert "failed" in _STATUS_LABELS


class TestPlaneStateMapping:
    def test_state_group_mapping(self):
        from backend.services.task_management.plane_manager import _STATUS_STATE_GROUP

        assert _STATUS_STATE_GROUP["in_progress"] == "started"
        assert _STATUS_STATE_GROUP["done"] == "completed"
        assert _STATUS_STATE_GROUP["failed"] == "cancelled"


class TestLinearStateMapping:
    def test_state_name_mapping(self):
        from backend.services.task_management.linear_manager import _STATUS_STATE_NAME

        assert _STATUS_STATE_NAME["in_progress"] == "In Progress"
        assert _STATUS_STATE_NAME["done"] == "Done"
        assert _STATUS_STATE_NAME["failed"] == "Canceled"


class TestNoOpManager:
    async def test_noop_update_status(self):
        manager = NoOpTaskManager()
        await manager.update_status({}, "done")  # should not raise

    async def test_noop_create_issue(self):
        manager = NoOpTaskManager()
        result = await manager.create_issue("ref", "title", "body")
        assert result == {"id": "", "url": ""}

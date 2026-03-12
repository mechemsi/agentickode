# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for AppSettingRepository."""

from backend.repositories.app_setting_repo import AppSettingRepository


class TestAppSettingRepository:
    async def test_get_returns_none_for_missing_key(self, db_session):
        repo = AppSettingRepository(db_session)
        assert await repo.get("nonexistent") is None

    async def test_set_creates_new_setting(self, db_session):
        repo = AppSettingRepository(db_session)
        row = await repo.set("theme", "dark")
        assert row.key == "theme"
        assert row.value == "dark"

    async def test_set_updates_existing_setting(self, db_session):
        repo = AppSettingRepository(db_session)
        await repo.set("theme", "dark")
        row = await repo.set("theme", "light")
        assert row.value == "light"

    async def test_get_returns_set_value(self, db_session):
        repo = AppSettingRepository(db_session)
        await repo.set("default_agents", ["claude", "aider"])
        value = await repo.get("default_agents")
        assert value == ["claude", "aider"]

    async def test_get_all_empty(self, db_session):
        repo = AppSettingRepository(db_session)
        result = await repo.get_all()
        assert result == {}

    async def test_get_all_returns_all_settings(self, db_session):
        repo = AppSettingRepository(db_session)
        await repo.set("key1", "val1")
        await repo.set("key2", {"nested": True})
        result = await repo.get_all()
        assert result == {"key1": "val1", "key2": {"nested": True}}

    async def test_set_stores_complex_json(self, db_session):
        repo = AppSettingRepository(db_session)
        value = {"agents": ["claude", "aider"], "enabled": True, "max": 5}
        await repo.set("config", value)
        assert await repo.get("config") == value
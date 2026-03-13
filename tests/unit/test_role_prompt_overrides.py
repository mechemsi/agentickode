# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for RolePromptOverride model, API endpoints, and resolve_prompts helper."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.models import RoleConfig, RolePromptOverride

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_role_config(agent_name: str = "coder") -> RoleConfig:
    return RoleConfig(
        agent_name=agent_name,
        display_name=agent_name.capitalize(),
        description="",
        system_prompt="default system prompt",
        user_prompt_template="default template {title}",
        is_system=True,
    )


def _make_cli_adapter(agent_name: str) -> MagicMock:
    adapter = MagicMock()
    adapter.agent_name = agent_name
    return adapter


def _make_ollama_adapter() -> MagicMock:
    """Adapter without agent_name — simulates OllamaAdapter."""
    adapter = MagicMock(spec=[])
    return adapter


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestRolePromptOverrideModel:
    async def test_create_override(self, db_session):
        """RolePromptOverride can be created and persisted."""
        config = _make_role_config()
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="claude",
            system_prompt="Custom claude system prompt",
            user_prompt_template="Custom template {title}",
            minimal_mode=False,
            extra_params={},
        )
        db_session.add(override)
        await db_session.commit()

        assert override.id is not None
        assert override.role_config_id == config.id
        assert override.cli_agent_name == "claude"
        assert override.system_prompt == "Custom claude system prompt"
        assert override.minimal_mode is False

    async def test_override_cascade_delete(self, db_session):
        """RolePromptOverride is deleted when the parent RoleConfig is deleted."""
        config = _make_role_config()
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="codex",
            minimal_mode=True,
        )
        db_session.add(override)
        await db_session.commit()
        override_id = override.id

        await db_session.delete(config)
        await db_session.commit()

        result = await db_session.execute(
            select(RolePromptOverride).where(RolePromptOverride.id == override_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_unique_constraint(self, db_session):
        """Cannot create two overrides for the same config + cli_agent_name."""
        config = _make_role_config()
        db_session.add(config)
        await db_session.commit()

        override1 = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="claude",
        )
        db_session.add(override1)
        await db_session.commit()

        override2 = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="claude",
        )
        db_session.add(override2)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_minimal_mode_defaults_false(self, db_session):
        """minimal_mode defaults to False."""
        config = _make_role_config()
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="aider",
        )
        db_session.add(override)
        await db_session.commit()

        assert override.minimal_mode is False

    async def test_relationship_back_populates(self, db_session):
        """RoleConfig.prompt_overrides returns the associated overrides."""
        from sqlalchemy.orm import selectinload

        config = _make_role_config()
        db_session.add(config)
        await db_session.commit()

        for agent in ["claude", "codex"]:
            db_session.add(RolePromptOverride(role_config_id=config.id, cli_agent_name=agent))
        await db_session.commit()

        result = await db_session.execute(
            select(RoleConfig)
            .options(selectinload(RoleConfig.prompt_overrides))
            .where(RoleConfig.id == config.id)
        )
        loaded = result.scalar_one()
        assert len(loaded.prompt_overrides) == 2
        names = {o.cli_agent_name for o in loaded.prompt_overrides}
        assert names == {"claude", "codex"}


# ---------------------------------------------------------------------------
# API Endpoint Tests
# ---------------------------------------------------------------------------


class TestListOverridesAPI:
    async def test_list_overrides_empty(self, client, db_session):
        """GET /role-configs/{name}/overrides returns empty list when none exist."""
        config = _make_role_config("planner")
        db_session.add(config)
        await db_session.commit()

        resp = await client.get("/api/role-configs/planner/overrides")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_overrides_returns_records(self, client, db_session):
        """GET /role-configs/{name}/overrides returns all overrides for that config."""
        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        for agent in ["claude", "codex"]:
            db_session.add(
                RolePromptOverride(
                    role_config_id=config.id,
                    cli_agent_name=agent,
                    minimal_mode=agent == "codex",
                )
            )
        await db_session.commit()

        resp = await client.get("/api/role-configs/coder/overrides")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {item["cli_agent_name"] for item in data}
        assert names == {"claude", "codex"}

    async def test_list_overrides_config_not_found(self, client):
        """GET /role-configs/{name}/overrides returns 404 when config missing."""
        resp = await client.get("/api/role-configs/nonexistent/overrides")
        assert resp.status_code == 404


class TestUpsertOverrideAPI:
    async def test_create_override(self, client, db_session):
        """PUT /role-configs/{name}/overrides/{agent} creates a new override."""
        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        payload = {
            "system_prompt": "Concise instructions only",
            "user_prompt_template": "Do: {title}",
            "minimal_mode": False,
            "extra_params": {},
        }
        resp = await client.put("/api/role-configs/coder/overrides/codex", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["cli_agent_name"] == "codex"
        assert data["system_prompt"] == "Concise instructions only"
        assert data["user_prompt_template"] == "Do: {title}"
        assert data["minimal_mode"] is False

    async def test_upsert_updates_existing(self, client, db_session):
        """PUT /role-configs/{name}/overrides/{agent} updates an existing override."""
        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="claude",
            system_prompt="Old prompt",
            minimal_mode=False,
        )
        db_session.add(override)
        await db_session.commit()

        payload = {
            "system_prompt": "New prompt",
            "user_prompt_template": None,
            "minimal_mode": True,
            "extra_params": {},
        }
        resp = await client.put("/api/role-configs/coder/overrides/claude", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["system_prompt"] == "New prompt"
        assert data["minimal_mode"] is True
        assert data["id"] == override.id  # same record updated

    async def test_upsert_minimal_mode(self, client, db_session):
        """PUT sets minimal_mode=True correctly."""
        config = _make_role_config("reviewer")
        db_session.add(config)
        await db_session.commit()

        payload = {
            "system_prompt": None,
            "user_prompt_template": "Just review: {title}",
            "minimal_mode": True,
            "extra_params": {},
        }
        resp = await client.put("/api/role-configs/reviewer/overrides/gemini", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["minimal_mode"] is True
        assert data["system_prompt"] is None

    async def test_upsert_config_not_found(self, client):
        """PUT /role-configs/{name}/overrides/{agent} returns 404 for unknown config."""
        resp = await client.put(
            "/api/role-configs/nonexistent/overrides/claude",
            json={"minimal_mode": False, "extra_params": {}},
        )
        assert resp.status_code == 404


class TestDeleteOverrideAPI:
    async def test_delete_override(self, client, db_session):
        """DELETE /role-configs/{name}/overrides/{agent} removes the override."""
        config = _make_role_config("planner")
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="claude",
        )
        db_session.add(override)
        await db_session.commit()

        resp = await client.delete("/api/role-configs/planner/overrides/claude")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted"}

        # Verify deletion
        result = await db_session.execute(
            select(RolePromptOverride).where(RolePromptOverride.id == override.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_override_not_found(self, client, db_session):
        """DELETE returns 404 when override does not exist."""
        config = _make_role_config("planner")
        db_session.add(config)
        await db_session.commit()

        resp = await client.delete("/api/role-configs/planner/overrides/claude")
        assert resp.status_code == 404

    async def test_delete_override_config_not_found(self, client):
        """DELETE returns 404 when the role config does not exist."""
        resp = await client.delete("/api/role-configs/nonexistent/overrides/claude")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# resolve_prompts Tests
# ---------------------------------------------------------------------------


class TestResolvePrompts:
    async def test_no_config_uses_fallbacks(self, db_session):
        """When config is None, fallbacks are returned."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        adapter = _make_cli_adapter("claude")
        sys, tmpl, _, _env = await resolve_prompts(
            None, adapter, db_session, "fallback sys", "fallback tmpl"
        )
        assert sys == "fallback sys"
        assert tmpl == "fallback tmpl"

    async def test_config_overrides_fallbacks(self, db_session):
        """When config has values, they override the fallbacks."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        adapter = _make_ollama_adapter()  # no agent_name
        sys, tmpl, _, _env = await resolve_prompts(
            config, adapter, db_session, "fallback sys", "fallback tmpl"
        )
        assert sys == "default system prompt"
        assert tmpl == "default template {title}"

    async def test_no_override_returns_config_values(self, db_session):
        """With no matching override, config values are returned for a CLI adapter."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        adapter = _make_cli_adapter("claude")
        sys, tmpl, _, _env = await resolve_prompts(
            config, adapter, db_session, "fallback sys", "fallback tmpl"
        )
        assert sys == "default system prompt"
        assert tmpl == "default template {title}"

    async def test_override_replaces_prompts(self, db_session):
        """When an override exists, its values replace config prompts."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="claude",
            system_prompt="Override system",
            user_prompt_template="Override template {title}",
            minimal_mode=False,
        )
        db_session.add(override)
        await db_session.commit()

        adapter = _make_cli_adapter("claude")
        sys, tmpl, _, _env = await resolve_prompts(
            config, adapter, db_session, "fallback sys", "fallback tmpl"
        )
        assert sys == "Override system"
        assert tmpl == "Override template {title}"

    async def test_minimal_mode_clears_system_prompt(self, db_session):
        """minimal_mode=True clears system_prompt entirely."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="codex",
            system_prompt="This should be ignored",
            user_prompt_template="Minimal template {title}",
            minimal_mode=True,
        )
        db_session.add(override)
        await db_session.commit()

        adapter = _make_cli_adapter("codex")
        sys, tmpl, _, _env = await resolve_prompts(
            config, adapter, db_session, "fallback sys", "fallback tmpl"
        )
        assert sys == ""
        assert tmpl == "Minimal template {title}"

    async def test_minimal_mode_no_template_keeps_existing(self, db_session):
        """minimal_mode=True with no user_template keeps the config template."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="gemini",
            user_prompt_template=None,
            minimal_mode=True,
        )
        db_session.add(override)
        await db_session.commit()

        adapter = _make_cli_adapter("gemini")
        sys, tmpl, _, _env = await resolve_prompts(
            config, adapter, db_session, "fallback sys", "fallback tmpl"
        )
        assert sys == ""
        assert tmpl == "default template {title}"

    async def test_non_cli_adapter_ignores_overrides(self, db_session):
        """Adapters without agent_name (Ollama) bypass override lookup."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        # Create an override that should NOT be applied
        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="claude",
            system_prompt="This should NOT be used",
            minimal_mode=True,
        )
        db_session.add(override)
        await db_session.commit()

        # Ollama adapter has no agent_name attribute
        adapter = _make_ollama_adapter()
        sys, tmpl, _, _env = await resolve_prompts(
            config, adapter, db_session, "fallback sys", "fallback tmpl"
        )
        # Should return config values, not the override
        assert sys == "default system prompt"
        assert tmpl == "default template {title}"

    async def test_partial_override_system_only(self, db_session):
        """Override with only system_prompt set leaves user_template unchanged."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config("reviewer")
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="aider",
            system_prompt="Custom aider system",
            user_prompt_template=None,
            minimal_mode=False,
        )
        db_session.add(override)
        await db_session.commit()

        adapter = _make_cli_adapter("aider")
        sys, tmpl, _, _env = await resolve_prompts(
            config, adapter, db_session, "fallback sys", "fallback tmpl"
        )
        assert sys == "Custom aider system"
        assert tmpl == "default template {title}"

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for F6: seed-defaults endpoint."""

from sqlalchemy import select

from backend.models import RoleConfig, RolePromptOverride


def _make_role_config(agent_name: str = "coder") -> RoleConfig:
    return RoleConfig(
        agent_name=agent_name,
        display_name=agent_name.capitalize(),
        description="",
        system_prompt="default system",
        user_prompt_template="default template",
        is_system=True,
    )


class TestSeedDefaults:
    async def test_seed_creates_overrides(self, client, db_session):
        """POST /role-configs/{name}/seed-defaults creates overrides for known agents."""
        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        resp = await client.post("/api/role-configs/coder/seed-defaults")
        assert resp.status_code == 200
        data = resp.json()

        assert set(data["created"]) == {"claude", "aider", "codex", "gemini-cli", "kimi"}
        assert data["skipped"] == []

        # Verify records exist
        result = await db_session.execute(
            select(RolePromptOverride).where(
                RolePromptOverride.role_config_id == config.id,
            )
        )
        overrides = result.scalars().all()
        assert len(overrides) == 5

        # Verify claude has minimal_mode=True
        claude_override = next(o for o in overrides if o.cli_agent_name == "claude")
        assert claude_override.minimal_mode is True
        assert claude_override.system_prompt is None

        # Verify aider has custom prompts
        aider_override = next(o for o in overrides if o.cli_agent_name == "aider")
        assert aider_override.minimal_mode is False
        assert aider_override.system_prompt is not None
        assert "Aider" in aider_override.system_prompt

    async def test_seed_idempotent(self, client, db_session):
        """Calling seed-defaults twice does not duplicate overrides."""
        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        resp1 = await client.post("/api/role-configs/coder/seed-defaults")
        assert resp1.status_code == 200
        assert len(resp1.json()["created"]) == 5

        resp2 = await client.post("/api/role-configs/coder/seed-defaults")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["created"] == []
        assert set(data2["skipped"]) == {"claude", "aider", "codex", "gemini-cli", "kimi"}

        # Still only 5 overrides
        result = await db_session.execute(
            select(RolePromptOverride).where(
                RolePromptOverride.role_config_id == config.id,
            )
        )
        assert len(result.scalars().all()) == 5

    async def test_seed_skips_existing(self, client, db_session):
        """Pre-existing overrides are skipped, new ones are created."""
        config = _make_role_config("coder")
        db_session.add(config)
        await db_session.commit()

        # Create one override manually
        existing = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="claude",
            system_prompt="Custom",
            minimal_mode=False,
        )
        db_session.add(existing)
        await db_session.commit()

        resp = await client.post("/api/role-configs/coder/seed-defaults")
        assert resp.status_code == 200
        data = resp.json()
        assert "claude" in data["skipped"]
        assert "claude" not in data["created"]
        assert len(data["created"]) == 4

        # Verify the existing override was NOT overwritten
        await db_session.refresh(existing)
        assert existing.system_prompt == "Custom"
        assert existing.minimal_mode is False

    async def test_seed_config_not_found(self, client):
        """Returns 404 when config doesn't exist."""
        resp = await client.post("/api/role-configs/nonexistent/seed-defaults")
        assert resp.status_code == 404

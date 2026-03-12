# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for /agents Agent Settings API."""

import pytest

from backend.models import AgentSettings, DiscoveredAgent, WorkspaceServer


def _make_agent(**overrides) -> AgentSettings:
    defaults = {
        "agent_name": "claude",
        "display_name": "Claude CLI",
        "description": "Test agent",
        "supports_session": True,
        "default_timeout": 600,
        "max_retries": 1,
        "environment_vars": {},
        "cli_flags": {},
        "enabled": True,
    }
    defaults.update(overrides)
    return AgentSettings(**defaults)


@pytest.mark.anyio
class TestAgentSettingsAPI:
    async def test_list_agents_empty(self, client):
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_agents_returns_seeded(self, client, db_session):
        db_session.add(_make_agent(agent_name="claude", display_name="Claude CLI"))
        db_session.add(_make_agent(agent_name="aider", display_name="Aider"))
        await db_session.commit()

        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {a["agent_name"] for a in data}
        assert names == {"claude", "aider"}

    async def test_list_agents_ordered_by_name(self, client, db_session):
        db_session.add(_make_agent(agent_name="opencode", display_name="OpenCode"))
        db_session.add(_make_agent(agent_name="aider", display_name="Aider"))
        db_session.add(_make_agent(agent_name="claude", display_name="Claude CLI"))
        await db_session.commit()

        resp = await client.get("/api/agents")
        data = resp.json()
        names = [a["agent_name"] for a in data]
        assert names == sorted(names)

    async def test_get_agent_found(self, client, db_session):
        db_session.add(_make_agent(agent_name="claude", display_name="Claude CLI"))
        await db_session.commit()

        resp = await client.get("/api/agents/claude")
        assert resp.status_code == 200
        assert resp.json()["agent_name"] == "claude"
        assert resp.json()["display_name"] == "Claude CLI"

    async def test_get_agent_not_found(self, client):
        resp = await client.get("/api/agents/nonexistent")
        assert resp.status_code == 404

    async def test_update_agent_display_name(self, client, db_session):
        db_session.add(_make_agent(agent_name="claude", display_name="Claude CLI"))
        await db_session.commit()

        resp = await client.put("/api/agents/claude", json={"display_name": "Claude Code"})
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Claude Code"

    async def test_update_agent_partial_update(self, client, db_session):
        db_session.add(
            _make_agent(
                agent_name="claude",
                display_name="Claude CLI",
                default_timeout=600,
                max_retries=1,
            )
        )
        await db_session.commit()

        resp = await client.put("/api/agents/claude", json={"default_timeout": 1200})
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_timeout"] == 1200
        # Other fields unchanged
        assert data["display_name"] == "Claude CLI"
        assert data["max_retries"] == 1

    async def test_update_agent_timeout_and_retries(self, client, db_session):
        db_session.add(_make_agent(agent_name="codex", display_name="Codex"))
        await db_session.commit()

        resp = await client.put(
            "/api/agents/codex",
            json={"default_timeout": 900, "max_retries": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_timeout"] == 900
        assert data["max_retries"] == 3

    async def test_update_agent_environment_vars(self, client, db_session):
        db_session.add(_make_agent(agent_name="claude", display_name="Claude CLI"))
        await db_session.commit()

        env = {"ANTHROPIC_API_KEY": "sk-test-123"}
        resp = await client.put("/api/agents/claude", json={"environment_vars": env})
        assert resp.status_code == 200
        assert resp.json()["environment_vars"] == env

    async def test_update_agent_cli_flags(self, client, db_session):
        db_session.add(_make_agent(agent_name="claude", display_name="Claude CLI"))
        await db_session.commit()

        flags = {"--model": "claude-opus-4-5", "--max-turns": "20"}
        resp = await client.put("/api/agents/claude", json={"cli_flags": flags})
        assert resp.status_code == 200
        assert resp.json()["cli_flags"] == flags

    async def test_update_agent_enabled_toggle(self, client, db_session):
        db_session.add(_make_agent(agent_name="aider", display_name="Aider", enabled=True))
        await db_session.commit()

        resp = await client.put("/api/agents/aider", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_update_agent_supports_session(self, client, db_session):
        db_session.add(
            _make_agent(agent_name="claude", display_name="Claude CLI", supports_session=True)
        )
        await db_session.commit()

        resp = await client.put("/api/agents/claude", json={"supports_session": False})
        assert resp.status_code == 200
        assert resp.json()["supports_session"] is False

    async def test_update_agent_not_found(self, client):
        resp = await client.put("/api/agents/unknown", json={"display_name": "X"})
        assert resp.status_code == 404

    async def test_get_availability_no_servers(self, client, db_session):
        db_session.add(_make_agent(agent_name="claude", display_name="Claude CLI"))
        await db_session.commit()

        resp = await client.get("/api/agents/claude/availability")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_availability_with_servers(self, client, db_session):
        server = WorkspaceServer(
            name="ws-1",
            hostname="10.0.0.1",
            port=22,
            username="root",
            workspace_root="/workspaces",
            status="online",
        )
        db_session.add(server)
        await db_session.flush()

        discovered = DiscoveredAgent(
            workspace_server_id=server.id,
            agent_name="claude",
            agent_type="cli_binary",
            path="/root/.local/bin/claude",
            version="1.2.3",
            available=True,
        )
        db_session.add(discovered)
        await db_session.commit()

        resp = await client.get("/api/agents/claude/availability")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["workspace_server_id"] == server.id
        assert data[0]["version"] == "1.2.3"
        assert data[0]["path"] == "/root/.local/bin/claude"

    async def test_get_availability_excludes_unavailable(self, client, db_session):
        server = WorkspaceServer(
            name="ws-2",
            hostname="10.0.0.2",
            port=22,
            username="root",
            workspace_root="/workspaces",
            status="online",
        )
        db_session.add(server)
        await db_session.flush()

        discovered = DiscoveredAgent(
            workspace_server_id=server.id,
            agent_name="aider",
            agent_type="cli_binary",
            path="/usr/local/bin/aider",
            version="0.9.0",
            available=False,
        )
        db_session.add(discovered)
        await db_session.commit()

        resp = await client.get("/api/agents/aider/availability")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_agent_settings_fields_in_response(self, client, db_session):
        db_session.add(
            _make_agent(
                agent_name="gemini",
                display_name="Google Gemini CLI",
                description="Gemini test",
                supports_session=False,
                default_timeout=300,
                max_retries=2,
                environment_vars={"GOOGLE_API_KEY": "key123"},
                cli_flags={"--model": "gemini-2.0"},
                enabled=True,
            )
        )
        await db_session.commit()

        resp = await client.get("/api/agents/gemini")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "gemini"
        assert data["display_name"] == "Google Gemini CLI"
        assert data["description"] == "Gemini test"
        assert data["supports_session"] is False
        assert data["default_timeout"] == 300
        assert data["max_retries"] == 2
        assert data["environment_vars"] == {"GOOGLE_API_KEY": "key123"}
        assert data["cli_flags"] == {"--model": "gemini-2.0"}
        assert data["enabled"] is True


@pytest.mark.anyio
class TestAgentSettingsSeed:
    async def test_seed_creates_defaults(self, db_session):
        from sqlalchemy import select

        from backend.seed import DEFAULT_AGENT_SETTINGS, _seed_agent_settings

        await _seed_agent_settings(db_session)

        result = await db_session.execute(select(AgentSettings).order_by(AgentSettings.agent_name))
        agents = result.scalars().all()
        agent_names = {a.agent_name for a in agents}
        expected = {d["agent_name"] for d in DEFAULT_AGENT_SETTINGS}
        assert agent_names == expected

    async def test_seed_is_idempotent(self, db_session):
        from sqlalchemy import select

        from backend.seed import DEFAULT_AGENT_SETTINGS, _seed_agent_settings

        await _seed_agent_settings(db_session)
        await _seed_agent_settings(db_session)

        result = await db_session.execute(select(AgentSettings))
        agents = result.scalars().all()
        assert len(agents) == len(DEFAULT_AGENT_SETTINGS)

    async def test_seed_preserves_existing_settings(self, db_session):
        from sqlalchemy import select

        from backend.seed import _seed_agent_settings

        db_session.add(
            _make_agent(
                agent_name="claude",
                display_name="Custom Claude",
                default_timeout=1200,
            )
        )
        await db_session.commit()

        await _seed_agent_settings(db_session)

        result = await db_session.execute(
            select(AgentSettings).where(AgentSettings.agent_name == "claude")
        )
        agent = result.scalar_one()
        # Custom values preserved — seed skips existing rows
        assert agent.display_name == "Custom Claude"
        assert agent.default_timeout == 1200
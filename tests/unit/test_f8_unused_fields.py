# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for F8: activating previously unused DB fields."""

from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PhaseExecution, RoleConfig, RolePromptOverride

# ---------------------------------------------------------------------------
# F8.1: get_phase_role with agent_override
# ---------------------------------------------------------------------------


class TestGetPhaseRole:
    def test_agent_override_takes_priority(self):
        """PhaseExecution.agent_override wins over phase_config and defaults."""
        from backend.worker.phases._helpers import get_phase_role

        pe = MagicMock(spec=PhaseExecution)
        pe.agent_override = "custom-agent"

        role = get_phase_role("coding", {"role": "coder"}, phase_execution=pe)
        assert role == "custom-agent"

    def test_fallback_to_phase_config(self):
        """When no agent_override, phase_config['role'] is used."""
        from backend.worker.phases._helpers import get_phase_role

        pe = MagicMock(spec=PhaseExecution)
        pe.agent_override = None

        role = get_phase_role("coding", {"role": "my-coder"}, phase_execution=pe)
        assert role == "my-coder"

    def test_fallback_to_default(self):
        """When no override and no config, default mapping is used."""
        from backend.worker.phases._helpers import get_phase_role

        pe = MagicMock(spec=PhaseExecution)
        pe.agent_override = None

        role = get_phase_role("coding", None, phase_execution=pe)
        assert role == "coder"

    def test_no_phase_execution(self):
        """When phase_execution is None, falls through to config/default."""
        from backend.worker.phases._helpers import get_phase_role

        role = get_phase_role("planning", None, phase_execution=None)
        assert role == "planner"

    def test_empty_string_override_ignored(self):
        """Empty string agent_override is treated as falsy."""
        from backend.worker.phases._helpers import get_phase_role

        pe = MagicMock(spec=PhaseExecution)
        pe.agent_override = ""

        role = get_phase_role("reviewing", None, phase_execution=pe)
        assert role == "reviewer"


# ---------------------------------------------------------------------------
# F8.2: _load_role_config with phase_binding
# ---------------------------------------------------------------------------


class TestLoadRoleConfigPhaseBinding:
    async def test_phase_bound_config_returned(self, db_session: AsyncSession):
        """A config with matching phase_binding is returned when queried by name."""
        from backend.services.role_resolver import RoleResolver

        bound = RoleConfig(
            agent_name="coder",
            display_name="Coder",
            phase_binding="coding",
            is_system=True,
        )
        db_session.add(bound)
        await db_session.commit()

        resolver = RoleResolver(factory=MagicMock(), http_client=MagicMock())
        config = await resolver._load_role_config("coder", db_session, phase_name="coding")
        assert config is not None
        assert config.id == bound.id

    async def test_fallback_to_unbound(self, db_session: AsyncSession):
        """When no phase-bound config exists, unbound config is returned."""
        from backend.services.role_resolver import RoleResolver

        unbound = RoleConfig(
            agent_name="coder",
            display_name="Coder",
            phase_binding=None,
            is_system=True,
        )
        db_session.add(unbound)
        await db_session.commit()

        resolver = RoleResolver(factory=MagicMock(), http_client=MagicMock())
        config = await resolver._load_role_config("coder", db_session, phase_name="reviewing")
        assert config is not None
        assert config.id == unbound.id

    async def test_no_phase_name_returns_unbound(self, db_session: AsyncSession):
        """When phase_name is None, unbound config is preferred."""
        from backend.services.role_resolver import RoleResolver

        unbound = RoleConfig(
            agent_name="coder",
            display_name="Coder",
            phase_binding=None,
            is_system=True,
        )
        db_session.add(unbound)
        await db_session.commit()

        resolver = RoleResolver(factory=MagicMock(), http_client=MagicMock())
        config = await resolver._load_role_config("coder", db_session, phase_name=None)
        assert config is not None
        assert config.id == unbound.id

    async def test_mismatched_binding_falls_through(self, db_session: AsyncSession):
        """A config with wrong phase_binding is still returned as last resort."""
        from backend.services.role_resolver import RoleResolver

        bound = RoleConfig(
            agent_name="coder",
            display_name="Coder",
            phase_binding="planning",
            is_system=True,
        )
        db_session.add(bound)
        await db_session.commit()

        resolver = RoleResolver(factory=MagicMock(), http_client=MagicMock())
        # Asking for "coding" phase but only "planning" binding exists
        config = await resolver._load_role_config("coder", db_session, phase_name="coding")
        assert config is not None
        assert config.id == bound.id

    async def test_no_config_returns_none(self, db_session: AsyncSession):
        """When no config exists at all, returns None."""
        from backend.services.role_resolver import RoleResolver

        resolver = RoleResolver(factory=MagicMock(), http_client=MagicMock())
        config = await resolver._load_role_config("nonexistent", db_session, phase_name="coding")
        assert config is None


# ---------------------------------------------------------------------------
# F8.3: resolve_prompts returns extra_params
# ---------------------------------------------------------------------------


def _make_role_config(agent_name: str = "coder") -> RoleConfig:
    return RoleConfig(
        agent_name=agent_name,
        display_name=agent_name.capitalize(),
        description="",
        system_prompt="default system",
        user_prompt_template="default template {title}",
        is_system=True,
    )


def _make_cli_adapter(agent_name: str) -> MagicMock:
    adapter = MagicMock()
    adapter.agent_name = agent_name
    return adapter


class TestResolvePromptsExtraParams:
    async def test_returns_empty_extra_params_by_default(self, db_session: AsyncSession):
        """When no extra_params on config or override, returns empty dict."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config()
        db_session.add(config)
        await db_session.commit()

        adapter = _make_cli_adapter("claude")
        sys, tmpl, extra, _env = await resolve_prompts(
            config, adapter, db_session, "fallback", "fallback"
        )
        assert extra == {}

    async def test_returns_config_extra_params(self, db_session: AsyncSession):
        """extra_params from RoleConfig are returned."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config()
        config.extra_params = {"timeout": 120}
        db_session.add(config)
        await db_session.commit()

        adapter = MagicMock(spec=[])  # no agent_name
        _, _, extra, _ = await resolve_prompts(config, adapter, db_session, "fallback", "fallback")
        assert extra == {"timeout": 120}

    async def test_override_extra_params_merge(self, db_session: AsyncSession):
        """Override extra_params are merged with config's (override wins on conflict)."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        config = _make_role_config()
        config.extra_params = {"timeout": 120, "keep": "yes"}
        db_session.add(config)
        await db_session.commit()

        override = RolePromptOverride(
            role_config_id=config.id,
            cli_agent_name="claude",
            extra_params={"timeout": 300, "new_key": "val"},
        )
        db_session.add(override)
        await db_session.commit()

        adapter = _make_cli_adapter("claude")
        _, _, extra, _ = await resolve_prompts(config, adapter, db_session, "fallback", "fallback")
        assert extra == {"timeout": 300, "keep": "yes", "new_key": "val"}

    async def test_no_config_returns_empty_extra_params(self, db_session: AsyncSession):
        """When config is None, extra_params is empty dict."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        adapter = _make_cli_adapter("claude")
        _, _, extra, _ = await resolve_prompts(None, adapter, db_session, "fallback", "fallback")
        assert extra == {}

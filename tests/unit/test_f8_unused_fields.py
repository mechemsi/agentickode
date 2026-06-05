# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for resolve_prompts extra_params return value."""

from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AgentSettings


def _make_cli_adapter(agent_name: str) -> MagicMock:
    adapter = MagicMock()
    adapter.agent_name = agent_name
    return adapter


class TestResolvePromptsExtraParams:
    async def test_returns_empty_extra_params_by_default(self, db_session: AsyncSession):
        """resolve_prompts always returns an empty extra_params dict."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        settings = AgentSettings(agent_name="claude", display_name="Claude CLI")
        adapter = _make_cli_adapter("claude")
        _sys, _tmpl, extra, _env = await resolve_prompts(
            settings, adapter, db_session, "fallback", "fallback"
        )
        assert extra == {}

    async def test_no_agent_settings_returns_empty_extra_params(self, db_session: AsyncSession):
        """When agent_settings is None, extra_params is empty dict."""
        from backend.worker.phases._prompt_resolver import resolve_prompts

        adapter = _make_cli_adapter("claude")
        _sys, _tmpl, extra, _env = await resolve_prompts(
            None, adapter, db_session, "fallback", "fallback"
        )
        assert extra == {}

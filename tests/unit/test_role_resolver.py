# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for RoleResolver — 5-step cascade resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.models import OllamaServer, RoleAssignment, WorkspaceServer
from backend.services.adapters.ollama_adapter import OllamaAdapter
from backend.services.role_resolver import ResolvedRole, RoleResolver


def _make_assignment(
    role="planner",
    provider_type="ollama",
    priority=0,
    workspace_server_id=None,
    ollama_server=None,
    model_name="model-x",
    agent_name=None,
    workspace_server=None,
    id_=1,
):
    a = MagicMock(spec=RoleAssignment)
    a.id = id_
    a.role = role
    a.provider_type = provider_type
    a.priority = priority
    a.workspace_server_id = workspace_server_id
    a.ollama_server_id = ollama_server.id if ollama_server else None
    a.ollama_server = ollama_server
    a.model_name = model_name
    a.agent_name = agent_name
    a.workspace_server = workspace_server
    return a


def _make_ollama_server(id_=1, name="gpu-01", url="http://localhost:11434"):
    s = MagicMock(spec=OllamaServer)
    s.id = id_
    s.name = name
    s.url = url
    return s


def _make_workspace_server(id_=1, name="ws-01"):
    s = MagicMock(spec=WorkspaceServer)
    s.id = id_
    s.name = name
    return s


class TestRoleResolver:
    async def test_settings_default_when_no_assignments(self, db_session):
        """Step 5: falls back to settings default when DB has no assignments."""
        factory = MagicMock()
        resolver = RoleResolver(factory=factory, http_client=MagicMock())

        with patch(
            "backend.services.http_client.get_http_client",
            return_value=MagicMock(),
        ):
            resolved = await resolver.resolve("planner", db_session)

        assert isinstance(resolved, ResolvedRole)
        assert isinstance(resolved.adapter, OllamaAdapter)
        assert "default" in resolved.adapter.provider_name

    async def test_global_primary_used(self, db_session):
        """Step 3: global primary assignment is used when available."""
        ollama = _make_ollama_server()
        assignment = _make_assignment(
            role="planner",
            provider_type="ollama",
            priority=0,
            workspace_server_id=None,
            ollama_server=ollama,
        )

        mock_adapter = AsyncMock()
        mock_adapter.is_available.return_value = True
        mock_adapter.provider_name = "ollama/model-x@gpu-01"

        factory = MagicMock()
        factory.create_ollama_adapter.return_value = mock_adapter

        resolver = RoleResolver(factory=factory, http_client=MagicMock())

        # Patch _load_candidates to return our test data
        resolver._load_candidates = AsyncMock(return_value=[assignment])

        result = await resolver.resolve("planner", db_session)

        assert result.adapter is mock_adapter
        factory.create_ollama_adapter.assert_called_once_with(ollama, "model-x")

    async def test_fallback_when_primary_unavailable(self, db_session):
        """Step 4: global fallback used when primary is unavailable."""
        ollama1 = _make_ollama_server(id_=1, name="gpu-01")
        ollama2 = _make_ollama_server(id_=2, name="gpu-02")

        primary = _make_assignment(role="planner", priority=0, ollama_server=ollama1, id_=1)
        fallback = _make_assignment(
            role="planner", priority=1, ollama_server=ollama2, model_name="fallback-model", id_=2
        )

        unavailable_adapter = AsyncMock()
        unavailable_adapter.is_available.return_value = False
        unavailable_adapter.provider_name = "ollama/model-x@gpu-01"

        available_adapter = AsyncMock()
        available_adapter.is_available.return_value = True
        available_adapter.provider_name = "ollama/fallback-model@gpu-02"

        factory = MagicMock()
        factory.create_ollama_adapter.side_effect = [unavailable_adapter, available_adapter]

        resolver = RoleResolver(factory=factory, http_client=MagicMock())
        resolver._load_candidates = AsyncMock(return_value=[primary, fallback])

        result = await resolver.resolve("planner", db_session)

        assert result.adapter is available_adapter

    async def test_server_specific_override(self, db_session):
        """Steps 1-2: server-specific assignments are tried before global."""
        ollama = _make_ollama_server()
        ws = _make_workspace_server()

        server_assignment = _make_assignment(
            role="coder",
            provider_type="agent",
            priority=0,
            workspace_server_id=ws.id,
            agent_name="claude",
            workspace_server=ws,
            ollama_server=None,
            model_name=None,
            id_=1,
        )
        global_assignment = _make_assignment(
            role="coder",
            priority=0,
            ollama_server=ollama,
            id_=2,
        )

        server_adapter = AsyncMock()
        server_adapter.is_available.return_value = True
        server_adapter.provider_name = "agent/claude@ws-01"

        factory = MagicMock()
        factory.create_agent_adapter.return_value = server_adapter

        resolver = RoleResolver(factory=factory, http_client=MagicMock())
        # Server-specific first, then global
        resolver._load_candidates = AsyncMock(return_value=[server_assignment, global_assignment])

        result = await resolver.resolve("coder", db_session, workspace_server_id=ws.id)

        assert result.adapter is server_adapter
        factory.create_agent_adapter.assert_called_once_with(
            "claude", workspace_server=ws, command_templates=None, needs_non_root=None
        )

    async def test_agent_adapter_resolution(self, db_session):
        """Agent assignments route to create_agent_adapter."""
        ws = _make_workspace_server()
        assignment = _make_assignment(
            role="coder",
            provider_type="agent",
            priority=0,
            agent_name="openhands",
            workspace_server=ws,
            ollama_server=None,
            model_name=None,
        )

        mock_adapter = AsyncMock()
        mock_adapter.is_available.return_value = True
        mock_adapter.provider_name = "agent/openhands"

        factory = MagicMock()
        factory.create_agent_adapter.return_value = mock_adapter

        resolver = RoleResolver(factory=factory, http_client=MagicMock())
        resolver._load_candidates = AsyncMock(return_value=[assignment])

        result = await resolver.resolve("coder", db_session)

        assert result.adapter is mock_adapter
        factory.create_agent_adapter.assert_called_once_with(
            "openhands", workspace_server=ws, command_templates=None, needs_non_root=None
        )

    async def test_build_adapter_failure_skips(self, db_session):
        """If factory raises, that candidate is skipped."""
        ollama = _make_ollama_server()
        assignment1 = _make_assignment(role="reviewer", priority=0, ollama_server=ollama, id_=1)
        assignment2 = _make_assignment(
            role="reviewer", priority=1, ollama_server=ollama, model_name="backup", id_=2
        )

        good_adapter = AsyncMock()
        good_adapter.is_available.return_value = True
        good_adapter.provider_name = "ollama/backup@gpu-01"

        factory = MagicMock()
        factory.create_ollama_adapter.side_effect = [RuntimeError("boom"), good_adapter]

        resolver = RoleResolver(factory=factory, http_client=MagicMock())
        resolver._load_candidates = AsyncMock(return_value=[assignment1, assignment2])

        result = await resolver.resolve("reviewer", db_session)

        assert result.adapter is good_adapter

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""AgentResolver — resolve a workflow step's agent directly (no role indirection).

A step names an agent (``phase_config['agent']``); when it doesn't, the per-project
default (``ProjectConfig.default_agent``) or the global default
(``AgentSettings.is_default``) is used, finally falling back to ``settings.default_agent``.
The adapter is built straight from ``AgentSettings`` via the shared ``AdapterFactory`` —
the same code path the old ``RoleResolver`` used, minus the role cascade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models import AgentSettings, ProjectConfig, WorkspaceServer
from backend.services.adapters.protocol import RoleAdapter

if TYPE_CHECKING:
    from backend.services.adapters.factory import AdapterFactory

logger = logging.getLogger("agentickode.agent_resolver")


@dataclass
class ResolvedAgent:
    """Result of resolving a step's agent — adapter plus its settings row."""

    adapter: RoleAdapter
    agent_settings: AgentSettings | None = None


class AgentResolver:
    """Resolve an agent name to a ready-to-use adapter."""

    def __init__(self, factory: AdapterFactory, http_client: object):
        self._factory = factory
        self._http_client = http_client

    async def resolve_agent(
        self,
        agent_name: str | None,
        session: AsyncSession,
        workspace_server_id: int | None = None,
        project_id: str | None = None,
    ) -> ResolvedAgent:
        name = await self._effective_agent_name(agent_name, session, project_id)
        agent_sett = await self._load_agent_settings(name, session)

        server: WorkspaceServer | None = None
        if workspace_server_id is not None:
            server = await session.get(WorkspaceServer, workspace_server_id)

        cmd_templates: dict | None = None
        non_root: bool | None = None
        if agent_sett is not None:
            if agent_sett.command_templates:
                cmd_templates = dict(agent_sett.command_templates)  # type: ignore[arg-type]
            non_root = getattr(agent_sett, "needs_non_root", None)

        adapter = self._factory.create_agent_adapter(
            name,
            workspace_server=server,
            command_templates=cmd_templates,
            needs_non_root=non_root,
        )
        logger.info("Resolved agent → %s", adapter.provider_name)
        return ResolvedAgent(adapter=adapter, agent_settings=agent_sett)

    async def _effective_agent_name(
        self,
        agent_name: str | None,
        session: AsyncSession,
        project_id: str | None,
    ) -> str:
        """Resolve the agent name: explicit → per-project → global default → constant."""
        if agent_name:
            return agent_name
        if project_id:
            project = await session.get(ProjectConfig, project_id)
            if project and project.default_agent:
                return str(project.default_agent)
        result = await session.execute(
            select(AgentSettings).where(AgentSettings.is_default.is_(True))
        )
        default_row = result.scalars().first()
        if default_row:
            return str(default_row.agent_name)
        return settings.default_agent

    async def _load_agent_settings(
        self, agent_name: str, session: AsyncSession
    ) -> AgentSettings | None:
        result = await session.execute(
            select(AgentSettings).where(AgentSettings.agent_name == agent_name)
        )
        return result.scalar_one_or_none()

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""RoleResolver — resolves a role to a concrete RoleAdapter via DB cascade."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.config import settings
from backend.models import AgentSettings, RoleAssignment, RoleConfig
from backend.services.adapters.ollama_adapter import OllamaAdapter
from backend.services.adapters.protocol import RoleAdapter
from backend.services.ollama_service import OllamaService

if TYPE_CHECKING:
    from backend.services.adapters.factory import AdapterFactory

logger = logging.getLogger("agentickode.role_resolver")


@dataclass
class ResolvedRole:
    """Result of resolving a role — adapter plus optional role config from DB."""

    adapter: RoleAdapter
    role_config: RoleConfig | None = None
    agent_settings: AgentSettings | None = None


# Default model per role — used as ultimate fallback from settings
_ROLE_MODEL_MAP = {
    "planner": lambda: settings.planner_model,
    "coder": lambda: settings.coder_model,
    "reviewer": lambda: settings.reviewer_model,
    "fast": lambda: settings.fast_model,
}


class RoleResolver:
    """Resolves a role string to a ready-to-use RoleAdapter.

    Resolution cascade (5 steps):
    1. Server-specific primary (workspace_server_id=X, priority=0)
    2. Server-specific fallback (workspace_server_id=X, priority=1)
    3. Global primary (workspace_server_id=NULL, priority=0)
    4. Global fallback (workspace_server_id=NULL, priority=1)
    5. Settings default — OllamaAdapter from settings.{role}_model
    """

    def __init__(self, factory: AdapterFactory, http_client: object):
        self._factory = factory
        self._http_client = http_client

    async def resolve(
        self,
        role: str,
        session: AsyncSession,
        workspace_server_id: int | None = None,
        phase_name: str | None = None,
    ) -> ResolvedRole:
        candidates = await self._load_candidates(role, session, workspace_server_id)
        role_config = await self._load_role_config(role, session, phase_name)
        tried: list[str] = []

        for assignment in candidates:
            # Pre-load AgentSettings for CLI agents to check enabled + pass templates
            agent_sett: AgentSettings | None = None
            cmd_templates: dict | None = None
            if assignment.provider_type == "agent" and assignment.agent_name:
                agent_sett = await self._load_agent_settings(assignment.agent_name, session)
                if agent_sett and not agent_sett.enabled:
                    tried.append(f"{assignment.agent_name}(disabled)")
                    logger.info(
                        "Agent '%s' is disabled, skipping for role '%s'",
                        assignment.agent_name,
                        role,
                    )
                    continue
                if agent_sett and agent_sett.command_templates:
                    cmd_templates = dict(agent_sett.command_templates)  # type: ignore[arg-type]

            # Pass needs_non_root from DB if available
            non_root: bool | None = None
            if agent_sett is not None:
                non_root = getattr(agent_sett, "needs_non_root", None)

            adapter = self._build_adapter(
                assignment, command_templates=cmd_templates, needs_non_root=non_root
            )
            if adapter is None:
                tried.append(f"{assignment.provider_type}:{assignment.agent_name or assignment.model_name}(build-failed)")
                continue

            try:
                if await adapter.is_available():
                    logger.info("Resolved role '%s' → %s", role, adapter.provider_name)
                    return ResolvedRole(
                        adapter=adapter,
                        role_config=role_config,
                        agent_settings=agent_sett,
                    )
                tried.append(f"{adapter.provider_name}(unavailable)")
                logger.info(
                    "Provider %s unavailable for role '%s', trying next",
                    adapter.provider_name,
                    role,
                )
            except Exception as exc:
                tried.append(f"{adapter.provider_name}(error: {exc})")
                logger.warning(
                    "Availability check failed for %s, trying next",
                    adapter.provider_name,
                    exc_info=True,
                )

        # Step 5: settings default — but warn clearly about what was tried
        if tried:
            logger.warning(
                "All configured providers failed for role '%s': %s — falling back to settings default (Ollama)",
                role,
                ", ".join(tried),
            )
        return ResolvedRole(adapter=self._settings_default(role), role_config=role_config)

    async def _load_role_config(
        self,
        role: str,
        session: AsyncSession,
        phase_name: str | None = None,
    ) -> RoleConfig | None:
        """Load the RoleConfig for the given role from DB.

        When phase_name is provided, prefer a config with matching phase_binding.
        Falls back to an unbound config (phase_binding IS NULL), then any config
        for the role regardless of phase_binding.
        """
        if phase_name:
            result = await session.execute(
                select(RoleConfig).where(
                    RoleConfig.agent_name == role,
                    RoleConfig.phase_binding == phase_name,
                )
            )
            bound = result.scalar_one_or_none()
            if bound:
                return bound
        # Prefer unbound config
        result = await session.execute(
            select(RoleConfig).where(
                RoleConfig.agent_name == role,
                RoleConfig.phase_binding.is_(None),
            )
        )
        unbound = result.scalar_one_or_none()
        if unbound:
            return unbound
        # Last resort: any config for this role
        result = await session.execute(select(RoleConfig).where(RoleConfig.agent_name == role))
        return result.scalar_one_or_none()

    async def _load_agent_settings(
        self,
        agent_name: str,
        session: AsyncSession,
    ) -> AgentSettings | None:
        """Load AgentSettings row for the given CLI agent name."""
        result = await session.execute(
            select(AgentSettings).where(AgentSettings.agent_name == agent_name)
        )
        return result.scalar_one_or_none()

    async def _load_candidates(
        self,
        role: str,
        session: AsyncSession,
        workspace_server_id: int | None,
    ) -> list[RoleAssignment]:
        """Load candidates in cascade order."""
        candidates: list[RoleAssignment] = []

        if workspace_server_id is not None:
            # Steps 1-2: server-specific (primary then fallback)
            stmt = (
                select(RoleAssignment)
                .options(
                    joinedload(RoleAssignment.ollama_server),
                    joinedload(RoleAssignment.workspace_server),
                )
                .where(
                    RoleAssignment.role == role,
                    RoleAssignment.workspace_server_id == workspace_server_id,
                )
                .order_by(RoleAssignment.priority)
            )
            result = await session.execute(stmt)
            candidates.extend(result.scalars().all())

        # Steps 3-4: global (primary then fallback)
        stmt = (
            select(RoleAssignment)
            .options(
                joinedload(RoleAssignment.ollama_server),
                joinedload(RoleAssignment.workspace_server),
            )
            .where(
                RoleAssignment.role == role,
                RoleAssignment.workspace_server_id.is_(None),
            )
            .order_by(RoleAssignment.priority)
        )
        result = await session.execute(stmt)
        candidates.extend(result.scalars().all())

        return candidates

    def _build_adapter(
        self,
        assignment: RoleAssignment,
        command_templates: dict | None = None,
        needs_non_root: bool | None = None,
    ) -> RoleAdapter | None:
        """Build an adapter from a RoleAssignment row."""
        try:
            if assignment.provider_type == "ollama":
                if assignment.ollama_server and assignment.model_name:
                    return self._factory.create_ollama_adapter(
                        assignment.ollama_server, assignment.model_name
                    )
            elif assignment.provider_type == "agent" and assignment.agent_name:
                return self._factory.create_agent_adapter(
                    assignment.agent_name,
                    workspace_server=assignment.workspace_server,
                    command_templates=command_templates,
                    needs_non_root=needs_non_root,
                )
        except Exception:
            logger.warning(
                "Failed to build adapter for assignment %d",
                assignment.id,
                exc_info=True,
            )
        return None

    def _settings_default(self, role: str) -> RoleAdapter:
        """Ultimate fallback: create OllamaAdapter from settings."""
        model_fn = _ROLE_MODEL_MAP.get(role)
        model = model_fn() if model_fn else settings.planner_model
        logger.info("Using settings default for role '%s': %s", role, model)
        from backend.services.http_client import get_http_client

        service = OllamaService(get_http_client())
        return OllamaAdapter(service, model, server_name="default")

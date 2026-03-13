# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""OpenHandsAdapter — wraps OpenHandsService as a role provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.openhands_service import OpenHandsService


class OpenHandsAdapter:
    """RoleAdapter implementation backed by OpenHands."""

    def __init__(self, openhands_service: OpenHandsService):
        self._service = openhands_service

    @property
    def provider_name(self) -> str:
        return "agent/openhands"

    async def generate(self, prompt: str, **kwargs: object) -> str:
        system_prompt = kwargs.get("system_prompt")
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        result = await self._service.run_agent(
            workspace="/tmp",
            instruction=full_prompt,
            max_iterations=1,
        )
        return result.get("output", "")

    async def run_task(self, workspace: str, instruction: str, **kwargs: object) -> dict:
        system_prompt = kwargs.get("system_prompt")
        full_instruction = f"{system_prompt}\n\n{instruction}" if system_prompt else instruction
        return await self._service.run_agent(
            workspace=workspace,
            instruction=full_instruction,
            max_iterations=int(kwargs.get("max_iterations", 20)),
        )

    async def is_available(self) -> bool:
        return await self._service.is_healthy()

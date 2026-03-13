# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""RoleAdapter protocol — unified interface for any role provider."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RoleAdapter(Protocol):
    """Unified interface for any role provider (LLM or agent)."""

    @property
    def provider_name(self) -> str:
        """Human-readable name, e.g. 'ollama/qwen2.5' or 'agent/claude'."""
        ...

    async def generate(self, prompt: str, **kwargs: object) -> str:
        """Generate text (for planner/reviewer roles)."""
        ...

    async def run_task(self, workspace: str, instruction: str, **kwargs: object) -> dict:
        """Run a coding task (for coder role)."""
        ...

    async def is_available(self) -> bool:
        """Check if this provider is currently reachable."""
        ...

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""OpenHands service — class-based replacement for openhands.py."""

import httpx

from backend.config import settings


class OpenHandsService:
    """Client for the OpenHands coding agent API."""

    def __init__(self, client: httpx.AsyncClient, base_url: str = ""):
        self._client = client
        self._base_url = base_url or settings.openhands_url

    async def run_agent(
        self,
        workspace: str,
        instruction: str,
        model: str | None = None,
        max_iterations: int = 20,
    ) -> dict:
        """Run an OpenHands agent on a workspace."""
        model = model or settings.coder_model
        resp = await self._client.post(
            f"{self._base_url}/api/agent/run",
            json={
                "workspace": workspace,
                "instruction": instruction,
                "model": model,
                "ollama_url": settings.ollama_url,
                "max_iterations": max_iterations,
                "auto_commit": True,
            },
            timeout=600.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_diff(self, workspace: str, base: str, head: str) -> str:
        """Get git diff between two refs via OpenHands."""
        resp = await self._client.get(
            f"{self._base_url}/api/git/diff",
            params={"workspace": workspace, "base": base, "head": head},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json().get("diff", "")

    async def run_tests(self, workspace: str, timeout_secs: int = 300) -> dict:
        """Run project tests via OpenHands."""
        resp = await self._client.post(
            f"{self._base_url}/api/workspace/run-tests",
            json={"workspace": workspace, "timeout": timeout_secs},
            timeout=float(timeout_secs + 60),
        )
        resp.raise_for_status()
        return resp.json()

    async def cleanup_workspace(self, workspace: str) -> None:
        """Cleanup a workspace via OpenHands."""
        await self._client.post(
            f"{self._base_url}/api/workspace/cleanup",
            json={"workspace": workspace},
            timeout=30.0,
        )

    async def create_branch(
        self, workspace: str, branch_name: str, base_branch: str = "main"
    ) -> None:
        """Create a git branch via OpenHands."""
        resp = await self._client.post(
            f"{self._base_url}/api/git/branch",
            json={
                "workspace": workspace,
                "branch_name": branch_name,
                "base_branch": base_branch,
            },
            timeout=60.0,
        )
        resp.raise_for_status()

    async def push_branch(self, workspace: str, branch: str) -> None:
        """Push a branch via OpenHands."""
        resp = await self._client.post(
            f"{self._base_url}/api/git/push",
            json={"workspace": workspace, "branch": branch},
            timeout=120.0,
        )
        resp.raise_for_status()

    async def is_healthy(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/api/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

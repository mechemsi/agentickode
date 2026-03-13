# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""AdapterFactory — creates RoleAdapter instances from DB models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.services.adapters.cli_adapter import CLIAdapter
from backend.services.adapters.ollama_adapter import OllamaAdapter
from backend.services.adapters.openhands_adapter import OpenHandsAdapter
from backend.services.adapters.protocol import RoleAdapter
from backend.services.ollama_service import OllamaService
from backend.services.workspace.ssh_service import SSHService

if TYPE_CHECKING:
    import httpx

    from backend.models import OllamaServer, WorkspaceServer
    from backend.services.openhands_service import OpenHandsService


class AdapterFactory:
    """Creates typed RoleAdapter instances from DB configuration."""

    def __init__(self, http_client: httpx.AsyncClient, openhands: OpenHandsService):
        self._client = http_client
        self._openhands = openhands

    def create_ollama_adapter(self, ollama_server: OllamaServer, model_name: str) -> RoleAdapter:
        service = OllamaService(self._client, base_url=ollama_server.url)
        return OllamaAdapter(service, model_name, server_name=ollama_server.name)

    def create_agent_adapter(
        self,
        agent_name: str,
        workspace_server: WorkspaceServer | None = None,
        command_templates: dict | None = None,
        needs_non_root: bool | None = None,
    ) -> RoleAdapter:
        if agent_name == "openhands":
            return OpenHandsAdapter(self._openhands)

        if workspace_server is None:
            raise ValueError(f"CLI agent '{agent_name}' requires a workspace server for SSH access")

        ssh = SSHService.for_server(workspace_server)
        worker_user = (
            workspace_server.worker_user
            if getattr(workspace_server, "worker_user_status", None) == "ready"
            else None
        )
        return CLIAdapter(
            ssh,
            agent_name,
            server_name=workspace_server.name,
            worker_user=worker_user,
            command_templates=command_templates,
            needs_non_root=needs_non_root,
        )

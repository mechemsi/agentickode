# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace server API subpackage."""

from backend.api.servers.agent_management import router as agent_management_router
from backend.api.servers.git_access import router as git_access_router
from backend.api.servers.projects import router as server_projects_router
from backend.api.servers.ssh_keys import router as ssh_keys_router
from backend.api.servers.worker_user import router as worker_user_router
from backend.api.servers.workspace_servers import router as workspace_servers_router
from backend.api.servers.workspace_servers_discovery import router as ws_discovery_router
from backend.api.servers.workspace_servers_ops import router as ws_ops_router

__all__ = [
    "agent_management_router",
    "git_access_router",
    "server_projects_router",
    "ssh_keys_router",
    "worker_user_router",
    "workspace_servers_router",
    "ws_discovery_router",
    "ws_ops_router",
]

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace subpackage — SSH, sandbox, agent, and project services for remote servers."""

from backend.services.workspace.agent_discovery import (
    API_AGENTS,
    CLI_AGENTS,
    AgentDiscoveryService,
    AgentInfo,
)
from backend.services.workspace.agent_install_service import (
    AgentInstallService,
    AgentStatus,
    InstallResult,
)
from backend.services.workspace.project_discovery import (
    SSH_REMOTE_RE,
    DiscoveredProject,
    ProjectDiscoveryService,
    parse_git_remote,
)
from backend.services.workspace.sandbox import (
    RemoteSandbox,
    RemoteSandboxError,
)
from backend.services.workspace.setup_service import (
    SETUP_STEPS,
    ServerSetupService,
    _get_setup_log,
    _step_entry,
)
from backend.services.workspace.ssh_service import (
    SSHCommandError,
    SSHService,
    SSHTestResult,
)
from backend.services.workspace.worker_user_service import (
    WorkerUserInfo,
    WorkerUserService,
)

__all__ = [
    "API_AGENTS",
    "CLI_AGENTS",
    "SETUP_STEPS",
    "SSH_REMOTE_RE",
    "AgentDiscoveryService",
    "AgentInfo",
    "AgentInstallService",
    "AgentStatus",
    "DiscoveredProject",
    "InstallResult",
    "ProjectDiscoveryService",
    "RemoteSandbox",
    "RemoteSandboxError",
    "SSHCommandError",
    "SSHService",
    "SSHTestResult",
    "ServerSetupService",
    "WorkerUserInfo",
    "WorkerUserService",
    "_get_setup_log",
    "_step_entry",
    "parse_git_remote",
]

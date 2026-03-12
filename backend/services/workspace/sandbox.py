# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Remote sandbox management via SSH — replaces local subprocess sandbox."""

from __future__ import annotations

import logging
import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("autodev.remote_sandbox")


class RemoteSandboxError(RuntimeError):
    """Raised when a remote sandbox operation fails."""


class RemoteSandbox:
    """Docker sandbox operations executed on a remote workspace server via SSH."""

    def __init__(
        self,
        ssh: SSHService,
        templates_path: str = "/opt/autodev/docker/sandboxes",
    ) -> None:
        self._ssh = ssh
        self._templates_path = templates_path

    async def start_sandbox(
        self,
        workspace: str,
        template: str,
        task_id: str,
        mount_points: dict[str, str] | None = None,
        env_vars: dict[str, str] | None = None,
        http_port: int = 8080,
    ) -> tuple[bool, str | None]:
        """Start a sandbox Docker environment on the remote server."""
        template_dir = f"{self._templates_path}/{template}"
        sandbox_dir = f"{workspace}/sandbox"

        # Verify template exists
        _, _, rc = await self._ssh.run_command(f"test -d {shlex.quote(template_dir)}", timeout=10)
        if rc != 0:
            logger.error(f"Sandbox template not found: {template_dir}")
            return False, None

        # Create sandbox dir and copy template
        copy_cmd = (
            f"mkdir -p {shlex.quote(sandbox_dir)} && "
            f"cp -r {shlex.quote(template_dir)}/. {shlex.quote(sandbox_dir)}/"
        )
        _, stderr, rc = await self._ssh.run_command(copy_cmd, timeout=30)
        if rc != 0:
            raise RemoteSandboxError(f"Failed to copy template: {stderr.strip()}")

        # Write .env file
        env_content = f"SANDBOX_HTTP_PORT={http_port}\\nCOMPOSE_PROJECT_NAME=sandbox-{task_id}\\n"
        for k, v in (env_vars or {}).items():
            env_content += f"{k}={v}\\n"
        env_cmd = f"printf {shlex.quote(env_content)} > {shlex.quote(sandbox_dir)}/.env"
        await self._ssh.run_command(env_cmd, timeout=10)

        # Start docker compose
        logger.info(f"Starting sandbox {template} for task {task_id}")
        up_cmd = f"cd {shlex.quote(sandbox_dir)} && docker compose up -d --build"
        _, stderr, rc = await self._ssh.run_command(up_cmd, timeout=600)
        if rc != 0:
            logger.error(f"Sandbox start failed: {stderr}")
            return False, None

        url = f"http://{self._ssh.hostname}:{http_port}"
        logger.info(f"Sandbox started at {url}")
        return True, url

    async def stop_sandbox(self, workspace_path: str) -> None:
        """Stop and remove sandbox containers on the remote server."""
        sandbox_dir = f"{workspace_path}/sandbox"
        compose_file = f"{sandbox_dir}/docker-compose.yml"

        # Check if compose file exists
        _, _, rc = await self._ssh.run_command(f"test -f {shlex.quote(compose_file)}", timeout=10)
        if rc != 0:
            return

        logger.info(f"Stopping sandbox at {sandbox_dir}")
        down_cmd = f"cd {shlex.quote(sandbox_dir)} && " f"docker compose down -v --remove-orphans"
        await self._ssh.run_command(down_cmd, timeout=120)
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Docker management service for remote workspace servers via SSH."""

from __future__ import annotations

import json
import logging
import shlex

from backend.services.workspace.command_executor import CommandExecutor

logger = logging.getLogger("agentickode.docker")


class DockerService:
    """Run Docker commands on a remote server via SSH."""

    def __init__(self, ssh: CommandExecutor):
        self._ssh = ssh

    async def _run(self, cmd: str, timeout: int = 30) -> str:
        """Run a command and return stdout. Raises on non-zero exit."""
        stdout, stderr, rc = await self._ssh.run_command(cmd, timeout=timeout)
        if rc != 0:
            msg = stderr.strip() or stdout.strip() or f"exit code {rc}"
            raise RuntimeError(f"Docker command failed: {msg}")
        return stdout

    async def list_containers(self, *, all: bool = True) -> list[dict]:
        """List containers using docker ps --format json."""
        flag = "-a" if all else ""
        stdout = await self._run(f"docker ps {flag} --format '{{{{json .}}}}'")
        return self._parse_json_lines(stdout)

    async def list_images(self) -> list[dict]:
        stdout = await self._run("docker images --format '{{json .}}'")
        return self._parse_json_lines(stdout)

    async def list_volumes(self) -> list[dict]:
        stdout = await self._run("docker volume ls --format '{{json .}}'")
        return self._parse_json_lines(stdout)

    async def list_networks(self) -> list[dict]:
        stdout = await self._run("docker network ls --format '{{json .}}'")
        return self._parse_json_lines(stdout)

    async def list_compose_stacks(self) -> list[dict]:
        """List docker compose stacks (projects)."""
        stdout = await self._run("docker compose ls --format json")
        try:
            data = json.loads(stdout)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return self._parse_json_lines(stdout)

    async def container_logs(self, container_id: str, tail: int = 100) -> str:
        safe_id = shlex.quote(container_id)
        stdout, stderr, _ = await self._ssh.run_command(
            f"docker logs --tail {tail} {safe_id} 2>&1", timeout=30
        )
        return stdout + stderr

    async def start_container(self, container_id: str) -> str:
        return await self._run(f"docker start {shlex.quote(container_id)}")

    async def stop_container(self, container_id: str) -> str:
        return await self._run(f"docker stop {shlex.quote(container_id)}", timeout=60)

    async def restart_container(self, container_id: str) -> str:
        return await self._run(f"docker restart {shlex.quote(container_id)}", timeout=60)

    async def remove_container(self, container_id: str, *, force: bool = False) -> str:
        f = "-f" if force else ""
        return await self._run(f"docker rm {f} {shlex.quote(container_id)}")

    async def remove_image(self, image_id: str, *, force: bool = False) -> str:
        f = "-f" if force else ""
        return await self._run(f"docker rmi {f} {shlex.quote(image_id)}")

    async def prune_containers(self) -> str:
        return await self._run("docker container prune -f", timeout=60)

    async def prune_images(self, *, all: bool = False) -> str:
        flag = "-a" if all else ""
        return await self._run(f"docker image prune -f {flag}", timeout=120)

    async def prune_volumes(self) -> str:
        return await self._run("docker volume prune -f", timeout=60)

    async def prune_networks(self) -> str:
        return await self._run("docker network prune -f", timeout=60)

    async def prune_system(self, *, all: bool = False, volumes: bool = False) -> str:
        flags: list[str] = []
        if all:
            flags.append("-a")
        if volumes:
            flags.append("--volumes")
        return await self._run(f"docker system prune -f {' '.join(flags)}", timeout=180)

    async def disk_usage(self) -> str:
        return await self._run("docker system df", timeout=30)

    async def container_inspect(self, container_id: str) -> dict:
        stdout = await self._run(f"docker inspect {shlex.quote(container_id)}")
        data = json.loads(stdout)
        return data[0] if data else {}

    @staticmethod
    def _parse_json_lines(text: str) -> list[dict]:
        """Parse newline-delimited JSON output from docker."""
        results: list[dict] = []
        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return results

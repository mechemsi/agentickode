# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Service for checking git provider SSH connectivity on workspace servers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.workspace.ssh_service import SSHService

DEFAULT_PROVIDERS = [
    ("github.com", "GitHub"),
    ("gitlab.com", "GitLab"),
    ("bitbucket.org", "Bitbucket"),
]


@dataclass
class ProviderStatus:
    host: str
    name: str
    connected: bool
    username: str | None = None
    error: str | None = None


@dataclass
class KeyInfo:
    has_key: bool
    public_key: str | None = None
    key_type: str | None = None


class GitAccessService:
    """Check git provider SSH access from a workspace server."""

    def __init__(self, ssh: SSHService):
        self._ssh = ssh

    async def _run(self, cmd: str, as_user: str | None = None, timeout: int = 10):
        if as_user:
            return await self._ssh.run_command_as(as_user, cmd, timeout=timeout)
        return await self._ssh.run_command(cmd, timeout=timeout)

    async def get_public_key(self, as_user: str | None = None) -> KeyInfo:
        """Check for existing SSH key on the workspace server."""
        for key_type, path in [
            ("ed25519", "~/.ssh/id_ed25519.pub"),
            ("rsa", "~/.ssh/id_rsa.pub"),
        ]:
            stdout, _, rc = await self._run(f"test -f {path} && cat {path}", as_user, timeout=10)
            if rc == 0 and stdout.strip():
                return KeyInfo(has_key=True, public_key=stdout.strip(), key_type=key_type)
        return KeyInfo(has_key=False)

    async def generate_key(
        self, server_name: str, force: bool = False, copy_to_user: str | None = None
    ) -> KeyInfo:
        """Generate an SSH key on the workspace server.

        If copy_to_user is provided, also copies the key pair to that user's ~/.ssh/
        so they have the same git provider access.
        """
        # Check if key already exists
        existing = await self.get_public_key()
        if existing.has_key and not force:
            if copy_to_user:
                await self._copy_key_to_user(copy_to_user)
            return existing

        force_flag = "-y" if force else ""
        comment = f"agentickode@{server_name}"
        cmd = f'ssh-keygen -t ed25519 -C "{comment}" -f ~/.ssh/id_ed25519 -N "" ' f"{force_flag} -q"
        _, stderr, rc = await self._ssh.run_command(cmd, timeout=15)
        if rc != 0:
            return KeyInfo(has_key=False)

        # Pre-accept common git host keys so clones work immediately
        await self._ssh.run_command(
            "ssh-keyscan -t ed25519 github.com gitlab.com bitbucket.org "
            ">> ~/.ssh/known_hosts 2>/dev/null; "
            "sort -u -o ~/.ssh/known_hosts ~/.ssh/known_hosts 2>/dev/null || true",
            timeout=15,
        )

        if copy_to_user:
            await self._copy_key_to_user(copy_to_user)

        return await self.get_public_key()

    async def _copy_key_to_user(self, username: str) -> None:
        """Copy root's SSH key pair and known_hosts to another user."""
        import shlex

        home = f"/home/{username}"
        safe_user = shlex.quote(username)
        cmd = (
            f"mkdir -p {home}/.ssh && chmod 700 {home}/.ssh && "
            f"cp -fL ~/.ssh/id_ed25519 {home}/.ssh/id_ed25519 2>/dev/null || true && "
            f"cp -fL ~/.ssh/id_ed25519.pub {home}/.ssh/id_ed25519.pub 2>/dev/null || true && "
            f"cp -fL ~/.ssh/id_rsa {home}/.ssh/id_rsa 2>/dev/null || true && "
            f"cp -fL ~/.ssh/id_rsa.pub {home}/.ssh/id_rsa.pub 2>/dev/null || true && "
            f"test -f ~/.ssh/known_hosts && cp -fL ~/.ssh/known_hosts {home}/.ssh/known_hosts 2>/dev/null || true ; "
            f"chmod 600 {home}/.ssh/id_* 2>/dev/null || true && "
            f"chown -R {safe_user}:{safe_user} {home}/.ssh"
        )
        await self._ssh.run_command(cmd, timeout=15)

    async def test_provider(
        self, host: str, name: str, as_user: str | None = None
    ) -> ProviderStatus:
        """Test SSH connectivity to a git provider."""
        cmd = (
            f"ssh -o StrictHostKeyChecking=accept-new "
            f"-o ConnectTimeout=5 -o BatchMode=yes "
            f"-T git@{host} 2>&1"
        )
        stdout, _, _ = await self._run(cmd, as_user, timeout=15)
        return _parse_ssh_output(host, name, stdout)

    async def check_all(
        self,
        custom_hosts: list[tuple[str, str]] | None = None,
        as_user: str | None = None,
    ) -> tuple[KeyInfo, list[ProviderStatus]]:
        """Check key and all provider connectivity. If as_user, run as that user."""
        key_info = await self.get_public_key(as_user)
        providers_to_check = list(DEFAULT_PROVIDERS)
        if custom_hosts:
            providers_to_check.extend(custom_hosts)

        statuses: list[ProviderStatus] = []
        if not key_info.has_key:
            # No key means all providers will fail — skip probing
            for host, name in providers_to_check:
                statuses.append(
                    ProviderStatus(host=host, name=name, connected=False, error="No SSH key found")
                )
            return key_info, statuses

        for host, name in providers_to_check:
            status = await self.test_provider(host, name, as_user)
            statuses.append(status)
        return key_info, statuses


def _parse_ssh_output(host: str, name: str, output: str) -> ProviderStatus:
    """Parse SSH -T output to determine connection status."""
    text = output.strip()

    # GitHub: "Hi {user}! You've successfully authenticated"
    m = re.search(r"Hi (\S+)! You've successfully authenticated", text)
    if m:
        return ProviderStatus(host=host, name=name, connected=True, username=m.group(1))

    # GitLab: "Welcome to GitLab, @{user}!"
    m = re.search(r"Welcome to GitLab, @(\S+?)!", text)
    if m:
        return ProviderStatus(host=host, name=name, connected=True, username=m.group(1))

    # Bitbucket: "logged in as {user}"
    m = re.search(r"logged in as (\S+)", text)
    if m:
        return ProviderStatus(host=host, name=name, connected=True, username=m.group(1))

    # Generic success patterns (self-hosted instances)
    if "successfully authenticated" in text.lower() or "welcome" in text.lower():
        return ProviderStatus(host=host, name=name, connected=True)

    # Permission denied
    error = text[:200] if text else "No response"
    return ProviderStatus(host=host, name=name, connected=False, error=error)

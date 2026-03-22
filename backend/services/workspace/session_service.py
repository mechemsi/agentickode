# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Manage persistent CLI sessions on workspace servers via tmux."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shlex

from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.sessions")


class SessionService:
    """Manage persistent CLI sessions on workspace servers via tmux."""

    def __init__(self, ssh: SSHService):
        self._ssh = ssh

    async def create_session(
        self,
        session_id: str,
        agent_name: str,
        user_context: str,
        workspace_path: str | None = None,
        tmux_name: str | None = None,
    ) -> dict:
        """Create a tmux session and launch an agent inside it."""
        tmux_name = tmux_name or f"{agent_name}-{session_id[:8]}"

        # Ensure tmux is installed
        _out, _err, rc_check = await self._ssh.run_command("command -v tmux")
        if rc_check != 0:
            await self._ssh.run_command(
                "apt-get update -qq && apt-get install -y -qq tmux >/dev/null 2>&1 "
                "|| yum install -y -q tmux 2>/dev/null "
                "|| apk add --no-cache tmux 2>/dev/null"
            )

        # Create tmux session
        stdout, stderr, rc = await self._ssh.run_command(
            f"tmux new-session -d -s {shlex.quote(tmux_name)} -x 200 -y 50"
        )
        if rc != 0:
            raise RuntimeError(f"Failed to create tmux session: {stderr.strip()}")

        # Build the agent launch command
        cd_cmd = f"cd {shlex.quote(workspace_path)} && " if workspace_path else ""

        if agent_name == "claude":
            agent_cmd = (
                f"{cd_cmd}claude --session-id {shlex.quote(session_id)} "
                "--dangerously-skip-permissions"
            )
        elif agent_name == "codex":
            agent_cmd = f"{cd_cmd}codex"
        else:
            agent_cmd = f"{cd_cmd}{agent_name}"

        # If running as non-root user
        if user_context and user_context != "root":
            agent_cmd = f"runuser -l {shlex.quote(user_context)} -c {shlex.quote(agent_cmd)}"

        # Send command into tmux
        await self._ssh.run_command(
            f"tmux send-keys -t {shlex.quote(tmux_name)} {shlex.quote(agent_cmd)} Enter"
        )

        # For Claude: enable remote control after a brief delay
        remote_control = False
        if agent_name == "claude":
            await asyncio.sleep(3)
            await self._ssh.run_command(
                f"tmux send-keys -t {shlex.quote(tmux_name)} "
                f"{shlex.quote('/remote-control enable')} Enter"
            )
            remote_control = True

        # Try to get PID
        pid = None
        try:
            stdout, _stderr, _rc = await self._ssh.run_command(
                f"tmux list-panes -t {shlex.quote(tmux_name)} -F '#{{pane_pid}}'"
            )
            pid_str = stdout.strip()
            if pid_str.isdigit():
                pid = int(pid_str)
        except Exception:
            pass

        return {
            "tmux_session": tmux_name,
            "pid": pid,
            "remote_control_enabled": remote_control,
        }

    async def check_session_alive(self, tmux_name: str) -> bool:
        """Check if a tmux session exists."""
        try:
            stdout, _stderr, _rc = await self._ssh.run_command(
                f"tmux has-session -t {shlex.quote(tmux_name)} 2>/dev/null "
                "&& echo 'alive' || echo 'dead'"
            )
            return "alive" in stdout
        except Exception:
            return False

    async def list_tmux_sessions(self) -> list[str]:
        """List all tmux session names on the server."""
        try:
            stdout, _stderr, _rc = await self._ssh.run_command(
                "tmux list-sessions -F '#{session_name}' 2>/dev/null || true"
            )
            output = stdout.strip()
            return [s for s in output.split("\n") if s.strip()] if output else []
        except Exception:
            return []

    async def send_command(self, tmux_name: str, message: str) -> str:
        """Send a command to a tmux session and capture output."""
        # Send the command
        await self._ssh.run_command(
            f"tmux send-keys -t {shlex.quote(tmux_name)} {shlex.quote(message)} Enter"
        )

        # Wait briefly for output
        await asyncio.sleep(2)

        # Capture pane content
        return await self.capture_output(tmux_name)

    async def capture_output(self, tmux_name: str, lines: int = 50) -> str:
        """Capture current tmux pane content."""
        try:
            stdout, _stderr, _rc = await self._ssh.run_command(
                f"tmux capture-pane -t {shlex.quote(tmux_name)} -p -S -{lines}"
            )
            return stdout
        except Exception as e:
            return f"Error capturing output: {e}"

    async def kill_session(self, tmux_name: str) -> None:
        """Kill a tmux session."""
        with contextlib.suppress(Exception):
            await self._ssh.run_command(f"tmux kill-session -t {shlex.quote(tmux_name)}")

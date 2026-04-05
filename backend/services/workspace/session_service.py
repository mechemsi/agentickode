# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Manage persistent CLI sessions on workspace servers via tmux."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shlex

from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.sessions")


class SessionService:
    """Manage persistent CLI sessions on workspace servers via tmux."""

    def __init__(self, ssh: SSHService, user: str | None = None):
        self._ssh = ssh
        self._user = user  # non-root user to run tmux as

    def _as_user(self, cmd: str) -> str:
        """Wrap a command to run as the target user if non-root."""
        if self._user and self._user != "root":
            return f"runuser -l {shlex.quote(self._user)} -c {shlex.quote(cmd)}"
        return cmd

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

        # Store user context for all subsequent tmux commands
        self._user = user_context

        # Pre-configure Claude settings to skip all interactive prompts
        if agent_name == "claude":
            await self._configure_claude(user_context, workspace_path)

        # Create tmux session as the target user, starting in workspace directory
        tmux_create = f"tmux new-session -d -s {shlex.quote(tmux_name)} -x 200 -y 50"
        if workspace_path:
            tmux_create += f" -c {shlex.quote(workspace_path)}"

        stdout, stderr, rc = await self._ssh.run_command(self._as_user(tmux_create))
        if rc != 0:
            raise RuntimeError(f"Failed to create tmux session: {stderr.strip()}")

        # Enable mouse scrolling and increase scrollback
        await self._ssh.run_command(
            self._as_user(
                f"tmux set-option -t {shlex.quote(tmux_name)} mouse on && "
                f"tmux set-option -t {shlex.quote(tmux_name)} history-limit 10000"
            )
        )

        # Build the agent launch command (tmux already in workspace dir)
        if agent_name == "claude":
            agent_cmd = (
                f"claude --dangerously-skip-permissions --session-id {shlex.quote(session_id)}"
            )
        elif agent_name == "codex":
            agent_cmd = "codex"
        else:
            agent_cmd = agent_name

        # Send command into user's tmux session
        await self._ssh.run_command(
            self._as_user(
                f"tmux send-keys -t {shlex.quote(tmux_name)} {shlex.quote(agent_cmd)} Enter"
            )
        )

        # For Claude: wait for startup then enable remote control
        remote_control = False
        if agent_name == "claude":
            remote_control = await self._wait_for_claude_ready(tmux_name)

        # Try to get PID
        pid = None
        try:
            stdout, _stderr, _rc = await self._ssh.run_command(
                self._as_user(f"tmux list-panes -t {shlex.quote(tmux_name)} -F '#{{pane_pid}}'")
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
                self._as_user(
                    f"tmux has-session -t {shlex.quote(tmux_name)} 2>/dev/null "
                    "&& echo 'alive' || echo 'dead'"
                )
            )
            return "alive" in stdout
        except Exception:
            return False

    async def list_tmux_sessions(self) -> list[str]:
        """List all tmux session names on the server."""
        try:
            stdout, _stderr, _rc = await self._ssh.run_command(
                self._as_user("tmux list-sessions -F '#{session_name}' 2>/dev/null || true")
            )
            output = stdout.strip()
            return [s for s in output.split("\n") if s.strip()] if output else []
        except Exception:
            return []

    async def send_command(self, tmux_name: str, message: str) -> str:
        """Send a command to a tmux session and capture output."""
        await self._ssh.run_command(
            self._as_user(
                f"tmux send-keys -t {shlex.quote(tmux_name)} {shlex.quote(message)} Enter"
            )
        )

        # Wait briefly for output
        await asyncio.sleep(2)

        # Capture pane content
        return await self.capture_output(tmux_name)

    async def capture_output(self, tmux_name: str, lines: int = 50) -> str:
        """Capture current tmux pane content."""
        try:
            stdout, _stderr, _rc = await self._ssh.run_command(
                self._as_user(f"tmux capture-pane -t {shlex.quote(tmux_name)} -p -S -{lines}")
            )
            return stdout
        except Exception as e:
            return f"Error capturing output: {e}"

    async def _configure_claude(
        self,
        user_context: str | None,
        workspace_path: str | None,
    ) -> None:
        """Pre-configure Claude settings to eliminate all interactive prompts.

        Sets up:
        - approvedDirectories: skip trust folder prompt
        - permissions allow all: skip all permission prompts (replaces --dangerously-skip-permissions)
        - bypassPermissions: accept the bypass warning
        """
        home_dir = f"/home/{user_context}" if user_context and user_context != "root" else "/root"

        settings_dir = f"{home_dir}/.claude"
        settings_file = f"{settings_dir}/settings.local.json"
        dirs_to_approve = [home_dir]
        if workspace_path:
            dirs_to_approve.append(workspace_path)

        # Read existing settings, merge our config
        read_cmd = f"cat {shlex.quote(settings_file)} 2>/dev/null || echo '{{}}'"
        stdout, _stderr, _rc = await self._ssh.run_command(read_cmd)

        try:
            settings = json.loads(stdout.strip())
        except (json.JSONDecodeError, ValueError):
            settings = {}

        # Approve directories
        existing = set(settings.get("approvedDirectories", []))
        existing.update(dirs_to_approve)
        settings["approvedDirectories"] = sorted(existing)

        # Allow all permissions so --dangerously-skip-permissions isn't needed
        settings["permissions"] = {
            "allow": [
                "Bash",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "WebFetch",
                "WebSearch",
                "mcp__*",
                "computer",
            ],
            "deny": [],
        }

        # Accept bypass permissions warning
        settings["bypassPermissions"] = True

        settings_json = json.dumps(settings, indent=2)
        owner = user_context if user_context and user_context != "root" else "root"
        write_cmd = (
            f"mkdir -p {shlex.quote(settings_dir)} && "
            f"cat > {shlex.quote(settings_file)} << 'AUTODEV_EOF'\n"
            f"{settings_json}\n"
            f"AUTODEV_EOF"
        )
        if owner != "root":
            write_cmd += f" && chown -R {shlex.quote(owner)}:{shlex.quote(owner)} {shlex.quote(settings_dir)}"

        await self._ssh.run_command(write_cmd)
        logger.debug("Configured Claude settings for %s: dirs=%s", owner, dirs_to_approve)

    async def _tmux_send(self, tmux_name: str, *keys: str) -> None:
        """Send one or more keys to a tmux session."""
        for key in keys:
            await self._ssh.run_command(
                self._as_user(f"tmux send-keys -t {shlex.quote(tmux_name)} {key}")
            )

    async def _wait_for_claude_ready(self, tmux_name: str, timeout: int = 30) -> bool:
        """Wait for Claude to start and handle any unexpected prompts.

        With settings pre-configured (approvedDirectories + permissions),
        Claude should start directly without interactive prompts.
        """
        # Poll until Claude is ready or we see an unexpected prompt
        for _i in range(timeout // 3):
            await asyncio.sleep(3)
            output = await self.capture_output(tmux_name, lines=40)
            logger.info("Claude startup check: %s", output[:300])

            # Fallback: handle any prompts that settings didn't prevent
            if "Yes, I trust this folder" in output:
                await self._tmux_send(tmux_name, "Enter")
                continue
            if "Bypass Permissions" in output and "Yes, I accept" in output:
                await self._tmux_send(tmux_name, "Down")
                await asyncio.sleep(1)
                await self._tmux_send(tmux_name, "Enter")
                continue

            # Claude is ready when we see the welcome or input area
            if any(marker in output for marker in ["Welcome", "/help", "/init", "Claude Code"]):
                logger.info("Claude is ready")
                break

            # Shell prompt means Claude exited
            if output.rstrip().endswith("$"):
                logger.warning("Claude exited back to shell")
                return False

        return True

    async def kill_session(self, tmux_name: str) -> None:
        """Kill a tmux session."""
        with contextlib.suppress(Exception):
            await self._ssh.run_command(
                self._as_user(f"tmux kill-session -t {shlex.quote(tmux_name)}")
            )

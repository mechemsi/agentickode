# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CLIAdapter — runs CLI agents via SSH on remote workspace servers."""

from __future__ import annotations

import json
import logging
import shlex
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from backend.services.adapters.cli_commands import (
    _CODER_USER,
    AGENT_COMMANDS,
)
from backend.services.adapters.cli_wrappers import (
    apply_cli_flags,
    apply_env_vars,
    wrap_generate_for_user,
)

if TYPE_CHECKING:
    from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.adapters.cli")

# Type alias for the optional log callback
LogFn = Callable[[str], Awaitable[None]]


async def _noop_log(_msg: str) -> None:
    """Default no-op log callback."""


class CLIAdapter:
    """RoleAdapter implementation that runs CLI agents via SSH."""

    def __init__(
        self,
        ssh_service: SSHService,
        agent_name: str,
        server_name: str = "",
        worker_user: str | None = None,
        command_templates: dict | None = None,
        needs_non_root: bool | None = None,
    ):
        self._ssh = ssh_service
        self._agent = agent_name
        self._server_name = server_name
        self._worker_user = worker_user

        if agent_name not in AGENT_COMMANDS:
            raise ValueError(f"Unknown CLI agent: {agent_name}")

        # Merge DB command templates over hardcoded defaults
        self._commands: dict[str, str | bool] = dict(AGENT_COMMANDS[agent_name])
        if command_templates:
            self._commands.update(command_templates)

        # Determine if agent needs non-root execution (from DB via RoleResolver).
        self._needs_non_root = bool(needs_non_root)

        # Token usage from last CLI invocation (parsed from JSON output)
        self._last_token_usage: tuple[int, int] | None = None

    @property
    def provider_name(self) -> str:
        label = f"agent/{self._agent}"
        if self._server_name:
            label += f"@{self._server_name}"
        return label

    @property
    def agent_name(self) -> str:
        return self._agent

    @property
    def ssh(self) -> SSHService:
        return self._ssh

    @property
    def worker_user(self) -> str | None:
        return self._worker_user

    @worker_user.setter
    def worker_user(self, value: str | None) -> None:
        self._worker_user = value

    @property
    def last_token_usage(self) -> tuple[int, int] | None:
        """Return (input_tokens, output_tokens) from last CLI invocation, if available."""
        return self._last_token_usage

    @property
    def supports_session(self) -> bool:
        """Return True if this agent supports session continuity."""
        return bool(self._commands.get("supports_session", False))

    def _parse_json_output(self, raw_stdout: str) -> str:
        """Parse JSON output from Claude CLI, extracting result text and token usage.

        Claude CLI with --output-format json returns a JSON object with:
        - result: the actual text output
        - input_tokens: tokens consumed in the prompt
        - output_tokens: tokens generated

        Returns the result text (or raw stdout if parsing fails).
        """
        self._last_token_usage = None
        stripped = raw_stdout.strip()
        if not stripped.startswith("{"):
            return raw_stdout

        try:
            data = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return raw_stdout

        # Extract token usage if present
        tokens_in = data.get("input_tokens")
        tokens_out = data.get("output_tokens")
        if isinstance(tokens_in, int) and isinstance(tokens_out, int):
            self._last_token_usage = (tokens_in, tokens_out)
            logger.info("Parsed token usage: in=%d out=%d", tokens_in, tokens_out)

        # Return the result text, falling back to raw stdout
        result = data.get("result")
        if isinstance(result, str):
            return result
        return raw_stdout

    def apply_command_overrides(self, overrides: dict[str, str]) -> None:
        """Merge per-phase command template overrides into this adapter's commands."""
        self._commands.update(overrides)

    async def _run_ssh(
        self, cmd: str, timeout: int, log_fn: LogFn, label: str
    ) -> tuple[str, str, int]:
        """Run SSH command with logging to both Python logger and UI callback."""
        await log_fn(f"[ssh] {label}: {cmd[:300]}")
        start = time.monotonic()
        stdout, stderr, rc = await self._ssh.run_command(cmd, timeout=timeout)
        elapsed = time.monotonic() - start
        await log_fn(f"[ssh] {label} done rc={rc} ({elapsed:.1f}s)")
        if stdout.strip():
            await log_fn(f"[ssh] {label} stdout: {stdout.strip()[:500]}")
        if stderr.strip():
            await log_fn(f"[ssh] {label} stderr: {stderr.strip()[:500]}")
        return stdout, stderr, rc

    async def generate(self, prompt: str, **kwargs: object) -> str:
        cmds = self._commands
        log_fn: LogFn = kwargs.get("log_fn") or _noop_log  # type: ignore[assignment]
        system_prompt = kwargs.get("system_prompt")
        session_id = kwargs.get("session_id")
        new_session: bool = kwargs.get("new_session", False)  # type: ignore[assignment]
        workspace = kwargs.get("workspace")

        # Only prepend system prompt when not continuing a session
        # (the existing session already carries the system prompt context)
        if system_prompt and not session_id:
            prompt = f"{system_prompt}\n\n{prompt}"

        # Write prompt to a temp file, then invoke agent
        escaped = prompt.replace("'", "'\\''")
        write_cmd = f'TMPF=$(mktemp) && echo \'{escaped}\' > "$TMPF" && echo "$TMPF"'
        stdout, _, rc = await self._run_ssh(write_cmd, 10, log_fn, "write-prompt")
        prompt_file = stdout.strip()

        # Use session variant if session_id provided and supported
        # workspace is required for session commands — Claude stores sessions per-project
        if session_id and workspace and cmds.get("supports_session"):
            if new_session and "generate_session_start" in cmds:
                # Start a brand new named session
                cmd = str(cmds["generate_session_start"]).format(
                    prompt_file=prompt_file,
                    session_id=session_id,
                    workspace=workspace,
                )
                await log_fn(
                    f"[agent] invoking {self._agent} generate (new session={str(session_id)[:8]}...)"
                )
            elif "generate_continue" in cmds:
                # Resume existing session
                cmd = str(cmds["generate_continue"]).format(
                    prompt_file=prompt_file,
                    session_id=session_id,
                    workspace=workspace,
                )
                await log_fn(
                    f"[agent] invoking {self._agent} generate (resume session={str(session_id)[:8]}...)"
                )
            else:
                cmd = str(cmds["generate"]).format(prompt_file=prompt_file)
                await log_fn(f"[agent] invoking {self._agent} generate")
        else:
            cmd = str(cmds["generate"]).format(prompt_file=prompt_file)
            await log_fn(f"[agent] invoking {self._agent} generate")

        # If SSH user is root and agent needs non-root (or worker_user is set), wrap
        # (session data lives under the coder user, so --resume must run as same user)
        if (self._needs_non_root or self._worker_user) and self._ssh.username == "root":
            if self._worker_user:
                cmd = wrap_generate_for_user(cmd, prompt_file, self._worker_user)
            else:
                cmd = wrap_generate_for_user(cmd, prompt_file, _CODER_USER)

        # Apply extra CLI flags and environment variables from AgentSettings
        extra_cli_flags: dict = kwargs.get("cli_flags", {})  # type: ignore[assignment]
        if extra_cli_flags:
            cmd = apply_cli_flags(cmd, extra_cli_flags)
        env_vars: dict = kwargs.get("environment_vars", {})  # type: ignore[assignment]
        if env_vars:
            cmd = apply_env_vars(cmd, env_vars)

        gen_timeout: int = kwargs.get("timeout", 300)  # type: ignore[assignment]
        start = time.monotonic()
        logger.info("[%s] generate start: %s", self._agent, cmd[:120])
        stdout, stderr, rc = await self._ssh.run_command(cmd, timeout=gen_timeout)
        elapsed = time.monotonic() - start
        logger.info("[%s] generate done in %.1fs (rc=%d)", self._agent, elapsed, rc)
        await log_fn(f"[agent] generate done in {elapsed:.1f}s (rc={rc})")
        if stderr.strip():
            await log_fn(f"[agent] generate stderr: {stderr.strip()[:300]}")

        # Cleanup temp file
        await self._ssh.run_command(f"rm -f {prompt_file}", timeout=5)

        if rc != 0:
            logger.warning("CLI generate failed (rc=%d, %.1fs): %s", rc, elapsed, stderr[:500])
        return self._parse_json_output(stdout)

    async def run_task(self, workspace: str, instruction: str, **kwargs: object) -> dict:
        from backend.services.adapters._cli_task_runner import run_cli_task

        return await run_cli_task(self, workspace, instruction, **kwargs)

    async def _detect_changed_files(self, workspace: str) -> list[str]:
        from backend.services.adapters._cli_task_runner import detect_changed_files

        return await detect_changed_files(self._ssh, workspace)

    async def close_session(self, session_id: str, workspace: str | None = None) -> None:
        from backend.services.adapters._cli_task_runner import close_cli_session

        await close_cli_session(self, session_id, workspace)

    async def is_available(self) -> bool:
        check_cmd = str(self._commands["check"])
        _, _, rc = await self._ssh.run_command(check_cmd, timeout=10)
        if rc == 0:
            return True
        # Agent may be installed for worker user only (e.g. /home/coder/.local/bin)
        if self._worker_user:
            wrapped = f"runuser -l {self._worker_user} -c {shlex.quote(check_cmd)}"
            _, _, rc = await self._ssh.run_command(wrapped, timeout=10)
            return rc == 0
        return False

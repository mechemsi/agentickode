# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Episode runner — orchestrates bounded autonomous agent episodes.

Each episode launches Claude Code with ``--max-turns`` and monitors the
stream-json output for completion, stalls, and context exhaustion.
Work is git-checkpointed between episodes for reliable recovery.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.services.adapters.cli_commands import AGENT_COMMANDS
from backend.services.stream_monitor import check_stall, poll_stream
from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.episode_runner")

# Poll interval for stream-json monitoring (seconds)
_POLL_INTERVAL = 5

# Maximum time to wait for an episode (seconds) — safety cap
_EPISODE_TIMEOUT = 5400


@dataclass
class EpisodeResult:
    """Outcome of a single episode execution."""

    completed: bool = False
    stalled: bool = False
    context_exhausted: bool = False
    max_turns_reached: bool = False
    turn_count: int = 0
    tokens_used: int = 0
    context_usage_pct: float = 0.0
    checkpoint_sha: str | None = None
    exit_code: int | None = None
    result_text: str = ""
    errors: list[str] = field(default_factory=list)


class EpisodeRunner:
    """Runs bounded agent episodes with monitoring and git checkpoints."""

    def __init__(
        self,
        ssh: SSHService,
        workspace: str,
        worker_user: str,
        log_fn: Callable | None = None,
    ):
        self._ssh = ssh
        self._workspace = workspace
        self._worker_user = worker_user
        self._log = log_fn or (lambda msg, **kw: None)

    async def run_episode(
        self,
        episode_num: int,
        session_id: str,
        max_turns: int = 30,
        *,
        context_summary: str | None = None,
        is_new_session: bool = False,
        stall_timeout: int = 600,
    ) -> EpisodeResult:
        """Run a single bounded episode.

        1. Write episode prompt to remote workspace
        2. Launch Claude via fire_and_forget with --max-turns
        3. Poll stream-json for progress, stalls, completion
        4. Git checkpoint on completion
        5. Return EpisodeResult with metrics
        """
        result = EpisodeResult()
        ws = shlex.quote(self._workspace)
        prompt_file = f"{self._workspace}/.autodev/episode_{episode_num}_prompt.md"

        # Write episode prompt
        prompt_content = await self._build_prompt(episode_num, context_summary, is_new_session)
        await self._write_remote_file(prompt_file, prompt_content)

        # Build and launch the agent command
        cmd = self._build_command(episode_num, session_id, max_turns, prompt_file, is_new_session)
        wrapped_cmd = self._wrap_for_user(cmd)

        self._log(f"Starting episode {episode_num} (max_turns={max_turns})")
        await self._ssh.run_command(
            f"chown -R {self._worker_user}:{self._worker_user} {ws}",
            timeout=60,
        )
        await self._ssh.fire_and_forget(wrapped_cmd)

        # Monitor until completion, stall, or timeout
        jsonl_path = f"{self._workspace}/.autodev/episode_{episode_num}.jsonl"
        exit_code_path = f"{self._workspace}/.autodev/episode_{episode_num}_exit_code"
        result = await self._monitor_episode(jsonl_path, exit_code_path, stall_timeout)

        # Git checkpoint
        sha = await self.git_checkpoint(f"WIP: episode {episode_num}")
        result.checkpoint_sha = sha

        self._log(
            f"Episode {episode_num} done: completed={result.completed}, "
            f"turns={result.turn_count}, stalled={result.stalled}"
        )
        return result

    async def _monitor_episode(
        self,
        jsonl_path: str,
        exit_code_path: str,
        stall_timeout: int,
    ) -> EpisodeResult:
        """Poll stream-json and exit code until episode ends."""
        result = EpisodeResult()
        offset = 1
        cumulative_turns = 0
        deadline = time.monotonic() + _EPISODE_TIMEOUT

        while time.monotonic() < deadline:
            await asyncio.sleep(_POLL_INTERVAL)

            # Check if agent has exited
            exit_code = await self._read_exit_code(exit_code_path)
            if exit_code is not None:
                result.exit_code = exit_code
                # Do a final stream poll to capture last metrics
                poll = await poll_stream(self._ssh, jsonl_path, offset)
                cumulative_turns += poll.turn_count
                result.turn_count = cumulative_turns
                result.context_usage_pct = max(result.context_usage_pct, poll.context_usage_pct)
                result.completed = poll.completed or exit_code == 0
                result.result_text = poll.result_text
                result.errors = poll.errors
                if not result.completed and exit_code == 0:
                    result.max_turns_reached = True
                return result

            # Poll stream for progress
            poll = await poll_stream(self._ssh, jsonl_path, offset)
            if poll.new_lines > 0:
                offset = poll.next_offset
                cumulative_turns += poll.turn_count
                result.turn_count = cumulative_turns
                result.context_usage_pct = max(result.context_usage_pct, poll.context_usage_pct)

            # Check for context exhaustion
            if result.context_usage_pct >= 90.0:
                result.context_exhausted = True
                self._log("Context usage >= 90%, ending episode early")
                await self.kill_agent()
                return result

            # Check for stall
            is_stalled = await check_stall(self._ssh, jsonl_path, stall_timeout)
            if is_stalled:
                result.stalled = True
                self._log(f"Stall detected (no output for {stall_timeout}s)")
                return result

        # Timeout
        result.stalled = True
        self._log("Episode timed out")
        await self.kill_agent()
        return result

    async def git_checkpoint(self, message: str) -> str | None:
        """Commit all workspace changes, return SHA or None if nothing to commit."""
        ws = shlex.quote(self._workspace)
        user = self._worker_user

        cmd = (
            f"cd {ws} && "
            f"git add -A && "
            f"git diff --cached --quiet || "
            f"git commit -m {shlex.quote(message)} --no-verify"
        )
        wrapped = (
            f"runuser -u {user} -- bash -c {shlex.quote(cmd)}"
            if self._ssh.username == "root"
            else cmd
        )

        stdout, _, rc = await self._ssh.run_command(wrapped, timeout=30)
        if rc != 0:
            return None

        # Get the SHA of the commit
        sha_cmd = f"cd {ws} && git rev-parse HEAD"
        sha_wrapped = (
            f"runuser -u {user} -- bash -c {shlex.quote(sha_cmd)}"
            if self._ssh.username == "root"
            else sha_cmd
        )
        sha_out, _, sha_rc = await self._ssh.run_command(sha_wrapped, timeout=10)
        return sha_out.strip() if sha_rc == 0 else None

    async def kill_agent(self) -> None:
        """Kill the running Claude process for this workspace."""
        ws = shlex.quote(self._workspace)
        # Kill any claude process whose cwd is the workspace
        await self._ssh.run_command(
            f"pkill -f 'claude.*{ws}' 2>/dev/null || true",
            timeout=10,
        )

    def _build_command(
        self,
        episode_num: int,
        session_id: str,
        max_turns: int,
        prompt_file: str,
        is_new_session: bool,
    ) -> str:
        """Build the claude CLI command for this episode."""
        templates = AGENT_COMMANDS.get("claude_episodic", {})
        template_key = "task" if is_new_session else "task_resume"
        template = str(templates.get(template_key, templates.get("task", "")))

        return template.format(
            workspace=self._workspace,
            max_turns=max_turns,
            session_id=session_id,
            prompt_file=prompt_file,
            episode_num=episode_num,
        )

    def _wrap_for_user(self, cmd: str) -> str:
        """Wrap command for non-root execution if needed."""
        if self._ssh.username != "root":
            return cmd
        user = self._worker_user
        user_path = (
            f"/home/{user}/.local/bin"
            f":/home/{user}/.claude/bin"
            ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        )
        inner = f"export PATH={shlex.quote(user_path)} && {cmd}"
        return f"runuser -u {user} -- bash -c {shlex.quote(inner)}"

    async def _build_prompt(
        self,
        episode_num: int,
        context_summary: str | None,
        is_new_session: bool,
    ) -> str:
        """Build the prompt for this episode."""
        if is_new_session or not context_summary:
            # First episode — use the main agent prompt
            ws = shlex.quote(self._workspace)
            stdout, _, rc = await self._ssh.run_command(
                f"cat {ws}/.autodev/agent_prompt.md 2>/dev/null",
                timeout=15,
            )
            return stdout if rc == 0 else "Continue working on the task."

        # Continuation episode
        ws = shlex.quote(self._workspace)
        diff_out, _, _ = await self._ssh.run_command(
            f"cd {ws} && git diff --stat HEAD~1 2>/dev/null || echo '(no diff)'",
            timeout=15,
        )

        return (
            f"# Continuation — Episode {episode_num}\n\n"
            f"## What was accomplished so far:\n{context_summary}\n\n"
            f"## Files changed since last checkpoint:\n```\n{diff_out}\n```\n\n"
            f"## Remaining task:\n"
            f"Continue working on the original task. Pick up where you left off.\n"
            f"Review the current state of the code and continue implementation.\n"
        )

    async def _write_remote_file(self, path: str, content: str) -> None:
        """Write content to a file on the remote server."""
        escaped = content.replace("'", "'\\''")
        await self._ssh.run_command(
            f"cat > {shlex.quote(path)} << 'AUTODEV_EOF'\n{escaped}\nAUTODEV_EOF",
            timeout=15,
        )

    async def _read_exit_code(self, path: str) -> int | None:
        """Read the exit code file, return int or None if not ready."""
        stdout, _, rc = await self._ssh.run_command(
            f"cat {shlex.quote(path)} 2>/dev/null",
            timeout=10,
        )
        if rc != 0 or not stdout.strip():
            return None
        try:
            return int(stdout.strip())
        except ValueError:
            return None

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Extracted heavy methods from CLIAdapter — run_task, detect_changed_files, close_session."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from backend.services.adapters.cli_commands import _CODER_USER
from backend.services.adapters.cli_wrappers import (
    apply_cli_flags,
    apply_env_vars,
    wrap_for_user,
    wrap_non_root,
)

if TYPE_CHECKING:
    from backend.services.adapters.cli_adapter import CLIAdapter, LogFn
    from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.adapters.cli")


async def detect_changed_files(ssh: SSHService, workspace: str) -> list[str]:
    """Get list of files changed by the agent (uncommitted + committed on branch)."""
    try:
        cmd = (
            f"cd {workspace} && ("
            f"git diff --name-only HEAD 2>/dev/null; "
            f"git diff --cached --name-only 2>/dev/null; "
            f"git ls-files --others --exclude-standard 2>/dev/null; "
            f"git diff --name-only $(git merge-base HEAD main 2>/dev/null || "
            f"git merge-base HEAD origin/main 2>/dev/null || echo HEAD~1)..HEAD 2>/dev/null"
            f") | sort -u"
        )
        stdout, _, rc = await ssh.run_command(cmd, timeout=10)
        if rc == 0 and stdout.strip():
            return [f.strip() for f in stdout.strip().split("\n") if f.strip()]
    except Exception:
        pass
    return []


async def run_cli_task(
    adapter: CLIAdapter, workspace: str, instruction: str, **kwargs: object
) -> dict:
    """Execute a CLI agent task via SSH, returning structured result dict."""
    from backend.services.adapters.cli_adapter import _noop_log

    cmds = adapter._commands
    log_fn: LogFn = kwargs.get("log_fn") or _noop_log  # type: ignore[assignment]
    system_prompt = kwargs.get("system_prompt")
    session_id = kwargs.get("session_id")

    # Only prepend system prompt when not continuing a session
    if system_prompt and not session_id:
        instruction = f"{system_prompt}\n\n{instruction}"

    # Check agent is available before writing files
    if not await adapter.is_available():
        msg = f"{adapter._agent} CLI not found on {adapter._ssh.hostname}"
        logger.error(msg)
        return {
            "output": "",
            "stderr": msg,
            "exit_code": 127,
            "files_changed": [],
            "session_id": None,
        }

    # Write instruction to temp file on remote
    escaped = instruction.replace("'", "'\\''")
    write_cmd = f'TMPF=$(mktemp) && echo \'{escaped}\' > "$TMPF" && echo "$TMPF"'
    stdout, _, _ = await adapter._run_ssh(write_cmd, 10, log_fn, "write-instruction")
    instruction_file = stdout.strip()

    # Choose command: session start, session continuation, or fresh start
    new_session: bool = kwargs.get("new_session", False)  # type: ignore[assignment]
    if session_id and cmds.get("supports_session"):
        if new_session and "task_session_start" in cmds:
            cmd = str(cmds["task_session_start"]).format(
                workspace=workspace,
                instruction_file=instruction_file,
                session_id=session_id,
            )
            logger.info(
                "[%s] task session start (session=%s) in %s",
                adapter._agent,
                str(session_id)[:8],
                workspace,
            )
        elif "task_continue" in cmds:
            cmd = str(cmds["task_continue"]).format(
                workspace=workspace,
                instruction_file=instruction_file,
                session_id=session_id,
            )
            logger.info(
                "[%s] task continue (session=%s) in %s",
                adapter._agent,
                str(session_id)[:8],
                workspace,
            )
        else:
            cmd = str(cmds["task"]).format(workspace=workspace, instruction_file=instruction_file)
            logger.info("[%s] task start in %s", adapter._agent, workspace)
    else:
        cmd = str(cmds["task"]).format(workspace=workspace, instruction_file=instruction_file)
        logger.info("[%s] task start in %s", adapter._agent, workspace)

    # If SSH user is root and agent needs non-root (or worker_user is set), wrap
    if (adapter._needs_non_root or adapter._worker_user) and adapter._ssh.username == "root":
        if adapter._worker_user:
            cmd = wrap_for_user(cmd, workspace, instruction_file, adapter._worker_user)
        else:
            cmd = wrap_non_root(cmd, workspace, instruction_file)

    # Apply extra CLI flags from AgentSettings if provided
    extra_cli_flags: dict = kwargs.get("cli_flags", {})  # type: ignore[assignment]
    if extra_cli_flags:
        cmd = apply_cli_flags(cmd, extra_cli_flags)

    # Prepend environment variables from AgentSettings if provided
    env_vars: dict = kwargs.get("environment_vars", {})  # type: ignore[assignment]
    if env_vars:
        cmd = apply_env_vars(cmd, env_vars)

    timeout: int = kwargs.get("timeout", 600)  # type: ignore[assignment]
    start = time.monotonic()
    stdout, stderr, rc = await adapter._run_ssh(cmd, timeout, log_fn, "agent-run")
    elapsed = time.monotonic() - start
    logger.info(
        "[%s] task done in %.1fs (rc=%d, %d chars output)",
        adapter._agent,
        elapsed,
        rc,
        len(stdout),
    )

    # Cleanup
    await adapter._run_ssh(f"rm -f {instruction_file}", 5, log_fn, "cleanup")

    # Detect files changed — uncommitted, staged, untracked, AND committed on branch
    detect_cmd = (
        f"cd {workspace} && ("
        f"git diff --name-only HEAD 2>/dev/null; "
        f"git diff --cached --name-only 2>/dev/null; "
        f"git ls-files --others --exclude-standard 2>/dev/null; "
        f"git diff --name-only $(git merge-base HEAD main 2>/dev/null || "
        f"git merge-base HEAD origin/main 2>/dev/null || echo HEAD~1)..HEAD 2>/dev/null"
        f") | sort -u"
    )
    diff_out, _, diff_rc = await adapter._run_ssh(detect_cmd, 10, log_fn, "git-diff")
    files_changed: list[str] = []
    if diff_rc == 0 and diff_out.strip():
        files_changed = [f.strip() for f in diff_out.strip().split("\n") if f.strip()]

    parsed_output = adapter._parse_json_output(stdout)

    return {
        "output": parsed_output,
        "stderr": stderr,
        "exit_code": rc,
        "elapsed_s": round(elapsed, 1),
        "files_changed": files_changed,
        "command": cmd,
        "session_id": session_id,
    }


async def close_cli_session(
    adapter: CLIAdapter, session_id: str, workspace: str | None = None
) -> None:
    """Clean up a CLI agent session to release any locks.

    This prevents "Session ID already in use" errors when sessions
    are reused across phases or when a previous invocation crashed.
    """
    if not session_id:
        return

    user = adapter._worker_user or (_CODER_USER if adapter._needs_non_root else "")

    # Determine home directory for session cleanup
    home = f"/home/{user}" if user and adapter._ssh.username == "root" else "~"

    # Remove any session lock/pid files that may prevent reuse.
    # Claude stores sessions under ~/.claude/projects/<hash>/.sessions/
    cleanup_cmd = (
        f"find {home}/.claude -path '*{session_id}*' "
        f"\\( -name '*.lock' -o -name '*.pid' \\) "
        f"-delete 2>/dev/null; "
        # Also kill any lingering agent process using this session
        f"pkill -f 'session-id {session_id}' 2>/dev/null; "
        f"pkill -f 'resume {session_id}' 2>/dev/null; "
        f"true"
    )
    try:
        await adapter._ssh.run_command(cleanup_cmd, timeout=10)
        logger.debug("[%s] closed session %s", adapter._agent, session_id[:8])
    except Exception:
        logger.debug("[%s] session cleanup failed (non-fatal)", adapter._agent)

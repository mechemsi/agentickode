# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent invocation for chat — one-shot per message with session resume.

Claude Code (and most CLI agents) are interactive CLIs, not stdin/stdout
pipes. The correct approach for programmatic chat:

  Message 1: claude -p "List projects" --session-id abc --output-format stream-json
  Message 2: claude -p "Create run"    --resume abc    --output-format stream-json

Each message = a separate process invocation. The --session-id / --resume
flag maintains conversation context between invocations.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shlex
import shutil
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass

logger = logging.getLogger("agentickode.chat.agent_process")

# System prompt for the conversational agent
SYSTEM_PROMPT = """\
You are the AI manager for AgenticKode, a coding automation platform.

You can control the platform through the available MCP tools:
- Create and manage projects (create_project, list_projects, get_project, update_project)
- Create and monitor task runs (create_run, list_runs, get_run, get_run_logs, cancel_run)
- Control running agents (send_message_to_agent, pause_agent, resume_agent, get_episodes)
- Approve or reject runs (approve_run, reject_run)
- Manage workspace servers (list_servers, add_server, setup_server, get_server_status)
- View analytics and health (get_analytics, get_health, list_agents)

When the user asks you to do something with code:
1. Identify which project they're referring to (use list_projects if unsure)
2. Create a task run with a clear, detailed description
3. Monitor progress and report back

Be conversational and proactive. If a run fails, investigate why and suggest next steps.
"""

# How each agent is invoked for a single message
# {message} and {session_id} are replaced at runtime
AGENT_COMMANDS: dict[str, dict[str, str]] = {
    "claude": {
        "new": (
            "claude -p {message}"
            " --output-format stream-json"
            " --session-id {session_id}"
            " --mcp-config {mcp_config}"
            " --dangerously-skip-permissions"
        ),
        "resume": (
            "claude -p {message}"
            " --output-format stream-json"
            " --resume {session_id}"
            " --mcp-config {mcp_config}"
            " --dangerously-skip-permissions"
        ),
        "check": "command -v claude",
    },
    "codex": {
        "new": "codex --quiet -p {message}",
        "resume": "codex --quiet -p {message}",
        "check": "command -v codex",
    },
    "gemini": {
        "new": "gemini -p {message}",
        "resume": "gemini -p {message}",
        "check": "command -v gemini",
    },
    "aider": {
        "new": "aider --yes --no-git --message {message}",
        "resume": "aider --yes --no-git --message {message}",
        "check": "command -v aider",
    },
}


@dataclass
class InvocationResult:
    """Result of a single agent invocation."""

    output: str
    exit_code: int
    stream_events: list[dict]


def _write_mcp_config(platform_url: str) -> str:
    """Write MCP config file pointing to the platform's SSE endpoint."""
    mcp_config = {
        "mcpServers": {
            "agentickode": {
                "type": "sse",
                "url": f"{platform_url}/mcp/sse",
            }
        }
    }
    config_fd, config_path = tempfile.mkstemp(suffix=".json", prefix="agentickode-mcp-")
    with os.fdopen(config_fd, "w") as f:
        json.dump(mcp_config, f)
    return config_path


def _write_message_file(message: str) -> str:
    """Write message to a temp file (avoids shell escaping issues)."""
    msg_fd, msg_path = tempfile.mkstemp(suffix=".txt", prefix="agentickode-msg-")
    with os.fdopen(msg_fd, "w") as f:
        f.write(message)
    return msg_path


def _wrap_runuser(cmd_str: str, run_as_user: str | None) -> str:
    """Wrap a shell command to run as ``run_as_user`` via ``runuser`` (login shell).

    No-op when ``run_as_user`` is falsy (runs as the backend process user — the
    pre-existing behaviour).
    """
    if not run_as_user:
        return cmd_str
    return f"runuser -l {shlex.quote(run_as_user)} -c {shlex.quote(cmd_str)}"


def _make_readable(*paths: str) -> None:
    """Make temp files readable by a non-root ``runuser`` child (0o644)."""
    for path in paths:
        with contextlib.suppress(OSError):
            os.chmod(path, 0o644)


def is_agent_available(agent_name: str) -> bool:
    """Check if an agent CLI is installed locally."""
    cmds = AGENT_COMMANDS.get(agent_name)
    if not cmds:
        return False
    check_cmd = cmds.get("check", "")
    binary = check_cmd.replace("command -v ", "")
    return shutil.which(binary) is not None


async def invoke_agent(
    agent_name: str,
    message: str,
    session_id: str,
    *,
    is_new_session: bool = True,
    platform_url: str = "http://localhost:8000",
    timeout: float = 120.0,
    run_as_user: str | None = None,
) -> InvocationResult:
    """Invoke an agent with a single message.

    Each call is a separate process. Session context is maintained
    via --session-id (first message) or --resume (subsequent).

    Args:
        agent_name: Agent to use (claude, codex, gemini, aider)
        message: User's message
        session_id: Session ID for conversation continuity
        is_new_session: True for first message, False for subsequent
        platform_url: Platform API URL for MCP tools
        timeout: Max seconds to wait for response

    Returns:
        InvocationResult with parsed output
    """
    cmds = AGENT_COMMANDS.get(agent_name)
    if not cmds:
        return InvocationResult(
            output=f"Unknown agent: {agent_name}",
            exit_code=1,
            stream_events=[],
        )

    if not is_agent_available(agent_name):
        return InvocationResult(
            output=f"Agent {agent_name} is not installed in this container",
            exit_code=1,
            stream_events=[],
        )

    # Write message to file to avoid shell escaping issues
    msg_path = _write_message_file(message)
    mcp_config_path = _write_mcp_config(platform_url)
    if run_as_user:
        _make_readable(msg_path, mcp_config_path)

    try:
        # Build command
        template = cmds["new"] if is_new_session else cmds["resume"]
        # For Claude, use file input instead of inline message
        if agent_name == "claude":
            cmd_str = template.replace("-p {message}", "").format(
                session_id=session_id,
                mcp_config=mcp_config_path,
            )
            # Pipe message file to stdin
            cmd_str = f"cat {msg_path} | {cmd_str.strip()}"
        else:
            cmd_str = template.format(
                message=msg_path,
                session_id=session_id,
                mcp_config=mcp_config_path,
            )

        cmd_str = _wrap_runuser(cmd_str, run_as_user)
        env = {**os.environ, "AGENTICKODE_URL": platform_url}

        logger.info("Invoking %s (session=%s, new=%s)", agent_name, session_id[:8], is_new_session)

        proc = await asyncio.create_subprocess_shell(
            cmd_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return InvocationResult(
                output="Agent timed out",
                exit_code=-1,
                stream_events=[],
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        exit_code = proc.returncode or 0

        # Parse stream-json output (Claude)
        output_text, events = _parse_stream_output(stdout, agent_name)

        return InvocationResult(
            output=output_text,
            exit_code=exit_code,
            stream_events=events,
        )

    finally:
        # Clean up temp files
        for path in (msg_path, mcp_config_path):
            with contextlib.suppress(OSError):
                os.unlink(path)


async def invoke_agent_streaming(
    agent_name: str,
    message: str,
    session_id: str,
    *,
    is_new_session: bool = True,
    platform_url: str = "http://localhost:8000",
    timeout: float = 120.0,
    run_as_user: str | None = None,
) -> AsyncIterator[str]:
    """Invoke an agent and stream output chunks as they arrive.

    Yields parsed text chunks for real-time display in the chat UI.
    """
    cmds = AGENT_COMMANDS.get(agent_name)
    if not cmds:
        yield f"Unknown agent: {agent_name}"
        return

    if not is_agent_available(agent_name):
        yield f"Agent {agent_name} is not installed in this container"
        return

    msg_path = _write_message_file(message)
    mcp_config_path = _write_mcp_config(platform_url)
    if run_as_user:
        _make_readable(msg_path, mcp_config_path)

    try:
        template = cmds["new"] if is_new_session else cmds["resume"]
        if agent_name == "claude":
            cmd_str = template.replace("-p {message}", "").format(
                session_id=session_id,
                mcp_config=mcp_config_path,
            )
            cmd_str = f"cat {msg_path} | {cmd_str.strip()}"
        else:
            cmd_str = template.format(
                message=msg_path,
                session_id=session_id,
                mcp_config=mcp_config_path,
            )

        cmd_str = _wrap_runuser(cmd_str, run_as_user)
        env = {**os.environ, "AGENTICKODE_URL": platform_url}

        proc = await asyncio.create_subprocess_shell(
            cmd_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        if not proc.stdout:
            yield "No output from agent"
            return

        while True:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                yield "\n[Agent timed out]"
                break

            if not line:
                break

            decoded = line.decode("utf-8", errors="replace").rstrip()
            if not decoded:
                continue

            # Parse stream-json for Claude
            if agent_name == "claude":
                try:
                    event = json.loads(decoded)
                    if isinstance(event, dict):
                        etype = event.get("type", "")
                        if etype == "assistant":
                            content = event.get("content", "")
                            if isinstance(content, str) and content:
                                yield content
                        elif etype == "result":
                            result = event.get("result", event.get("content", ""))
                            if result:
                                yield result
                            break
                        elif etype == "tool_use":
                            tool = event.get("tool", event.get("name", ""))
                            yield f"\n[Using tool: {tool}]\n"
                        elif etype == "tool_result":
                            pass  # Skip raw tool results
                except json.JSONDecodeError:
                    yield decoded
            else:
                yield decoded

        await proc.wait()

    finally:
        for path in (msg_path, mcp_config_path):
            with contextlib.suppress(OSError):
                os.unlink(path)


def _parse_stream_output(stdout: str, agent_name: str) -> tuple[str, list[dict]]:
    """Parse agent output, extracting text and stream events."""
    if agent_name != "claude":
        return stdout.strip(), []

    events: list[dict] = []
    text_parts: list[str] = []

    for line in stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
                etype = event.get("type", "")
                if etype == "result":
                    text_parts.append(event.get("result", event.get("content", "")))
                elif etype == "assistant":
                    content = event.get("content", "")
                    if isinstance(content, str):
                        text_parts.append(content)
        except json.JSONDecodeError:
            text_parts.append(line)

    return "\n".join(text_parts).strip(), events

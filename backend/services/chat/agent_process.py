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

from backend.services.workspace.usernames import validate_username

logger = logging.getLogger("agentickode.chat.agent_process")


def _maybe_wrap_runuser(
    cmd_str: str,
    *,
    worker_user: str | None,
    platform_url: str,
    readable_paths: tuple[str, ...] = (),
) -> str:
    """Wrap ``cmd_str`` so it runs as ``worker_user`` via ``runuser -l``.

    No-op when ``worker_user`` is falsy, equals the current process user,
    or the backend isn't running as root (``runuser`` would just fail).

    ``runuser -l`` simulates a full login (HOME / PATH for the target
    user) so Claude can find ``~/.claude/`` and the agent binary on the
    user's PATH. The cost is that the caller's env is wiped — we
    re-export the variables the agent actually needs inside the wrapped
    command.

    Tempfiles created by the parent process are owned by root with mode
    0600 by default; ``chmod 0644`` widens them so the worker user can
    read them via ``cat`` / ``--mcp-config``.
    """
    if not worker_user:
        return cmd_str
    validate_username(worker_user, field="platform server worker_user")
    if os.geteuid() != 0:
        return cmd_str
    try:
        if worker_user == os.getlogin():
            return cmd_str
    except OSError:
        pass

    for path in readable_paths:
        with contextlib.suppress(OSError):
            os.chmod(path, 0o644)

    # Re-export the env vars the agent reads; ``runuser -l`` strips
    # everything else. Keep this list tight — anything not exported here
    # is invisible to the agent process.
    env_prefix = f"export AGENTICKODE_URL={shlex.quote(platform_url)}; "
    inner = env_prefix + cmd_str
    return f"runuser -l {shlex.quote(worker_user)} -c {shlex.quote(inner)}"


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


def _mcp_config_json(platform_url: str) -> str:
    """Serialize the MCP config that points Claude at our /mcp/sse endpoint."""
    return json.dumps(
        {
            "mcpServers": {
                "agentickode": {
                    "type": "sse",
                    "url": f"{platform_url}/mcp/sse",
                }
            }
        }
    )


def _write_mcp_config(platform_url: str) -> str:
    """Write MCP config file pointing to the platform's SSE endpoint."""
    config_fd, config_path = tempfile.mkstemp(suffix=".json", prefix="agentickode-mcp-")
    with os.fdopen(config_fd, "w") as f:
        f.write(_mcp_config_json(platform_url))
    return config_path


def _write_message_file(message: str) -> str:
    """Write message to a temp file (avoids shell escaping issues)."""
    msg_fd, msg_path = tempfile.mkstemp(suffix=".txt", prefix="agentickode-msg-")
    with os.fdopen(msg_fd, "w") as f:
        f.write(message)
    return msg_path


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
    worker_user: str | None = None,
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
        worker_user: If set, wrap the agent command in ``runuser -l`` so
            it runs as that OS user instead of the backend's process
            user. No-op when unset, when it matches the current user,
            or when the backend isn't root (``runuser`` would fail).

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

        env = {**os.environ, "AGENTICKODE_URL": platform_url}

        cmd_str = _maybe_wrap_runuser(
            cmd_str,
            worker_user=worker_user,
            platform_url=platform_url,
            readable_paths=(msg_path, mcp_config_path),
        )

        logger.info(
            "Invoking %s (session=%s, new=%s, run_as=%s)",
            agent_name,
            session_id[:8],
            is_new_session,
            worker_user or "(self)",
        )

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
    worker_user: str | None = None,
) -> AsyncIterator[str]:
    """Invoke an agent and stream output chunks as they arrive.

    Yields parsed text chunks for real-time display in the chat UI.
    ``worker_user`` mirrors :func:`invoke_agent` — wraps the command in
    ``runuser -l`` when set, no-op otherwise.
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

        env = {**os.environ, "AGENTICKODE_URL": platform_url}

        cmd_str = _maybe_wrap_runuser(
            cmd_str,
            worker_user=worker_user,
            platform_url=platform_url,
            readable_paths=(msg_path, mcp_config_path),
        )

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


async def invoke_agent_via_bridge(
    bridge,
    agent_name: str,
    message: str,
    session_id: str,
    *,
    is_new_session: bool = True,
    platform_url: str = "http://localhost:8000",
    timeout: float = 120.0,
) -> InvocationResult:
    """Invoke an agent on the host via the host bridge daemon.

    ``bridge`` is a :class:`HostBridgeService` instance. Behaves like
    :func:`invoke_agent` but the actual subprocess runs on the host
    (using the host's PATH, Claude install, and user) instead of in
    the backend container.

    The MCP config JSON is written to a host-side temp file via the
    bridge's ``/write_tempfile`` endpoint so ``--mcp-config <path>``
    resolves correctly. The user's message is piped via the bridge's
    ``stdin`` parameter — no need to share /tmp between container
    and host.
    """
    cmds = AGENT_COMMANDS.get(agent_name)
    if not cmds:
        return InvocationResult(
            output=f"Unknown agent: {agent_name}", exit_code=1, stream_events=[]
        )

    mcp_path = await bridge.write_tempfile(_mcp_config_json(platform_url), suffix=".json")

    template = cmds["new"] if is_new_session else cmds["resume"]
    if agent_name == "claude":
        # Drop ``-p {message}`` — the message arrives on stdin.
        cmd_str = template.replace("-p {message}", "").format(
            session_id=session_id, mcp_config=mcp_path
        )
        cmd_str = cmd_str.strip()
    else:
        # Non-Claude agents take a message file path on the command
        # line. Write the message to a host-side temp file too.
        msg_path = await bridge.write_tempfile(message, suffix=".txt")
        cmd_str = template.format(message=msg_path, session_id=session_id, mcp_config=mcp_path)

    logger.info(
        "Invoking %s via bridge (session=%s, new=%s)",
        agent_name,
        session_id[:8],
        is_new_session,
    )

    try:
        stdout, _stderr, exit_code = await bridge.run_command_with_stdin(
            cmd_str,
            stdin=message if agent_name == "claude" else "",
            timeout=int(timeout),
            env={"AGENTICKODE_URL": platform_url},
        )
    except Exception as exc:
        return InvocationResult(
            output=f"Host bridge invocation failed: {exc}",
            exit_code=1,
            stream_events=[],
        )

    output_text, events = _parse_stream_output(stdout, agent_name)
    return InvocationResult(output=output_text, exit_code=exit_code, stream_events=events)

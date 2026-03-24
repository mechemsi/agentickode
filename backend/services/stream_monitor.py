# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Stream-JSON monitor for Claude Code autonomous episodes.

Tails remote JSONL files written by Claude's --output-format stream-json
and extracts execution metrics (turn count, context usage, completion).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.stream_monitor")


@dataclass
class StreamPollResult:
    """Metrics from a single poll of the stream-json JSONL file."""

    new_lines: int = 0
    next_offset: int = 0
    turn_count: int = 0
    context_usage_pct: float = 0.0
    completed: bool = False
    result_text: str = ""
    last_activity_ts: float = 0.0
    errors: list[str] = field(default_factory=list)


async def poll_stream(
    ssh: SSHService,
    jsonl_path: str,
    last_offset: int = 0,
) -> StreamPollResult:
    """Read new lines from a remote JSONL file and extract metrics.

    Uses ``tail -n +{offset}`` to read only new lines since last poll.
    Parses Claude's stream-json format for turn counts, context usage,
    and completion signals.

    Args:
        ssh: SSH connection to the remote workspace server.
        jsonl_path: Absolute path to the episode JSONL file on remote.
        last_offset: Line number to start reading from (1-based).

    Returns:
        StreamPollResult with extracted metrics and the next offset.
    """
    result = StreamPollResult(last_activity_ts=time.time())

    # Read new lines from remote JSONL file
    offset = max(last_offset, 1)
    stdout, _, rc = await ssh.run_command(
        f"tail -n +{offset} {jsonl_path} 2>/dev/null | head -500",
        timeout=15,
    )

    if rc != 0 or not stdout.strip():
        result.next_offset = offset
        return result

    lines = stdout.strip().split("\n")
    result.new_lines = len(lines)
    result.next_offset = offset + len(lines)

    turn_count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(event, dict):
            continue

        result.last_activity_ts = time.time()
        event_type = event.get("type", "")

        # Count assistant turns
        if event_type == "assistant":
            turn_count += 1

        # Track context window usage
        if event_type == "system" and event.get("subtype") == "context_window":
            pct = event.get("usage_pct", 0.0)
            if isinstance(pct, int | float):
                result.context_usage_pct = float(pct)

        # Detect completion
        if event_type == "result":
            result.completed = True
            result.result_text = event.get("result", event.get("content", ""))

        # Capture errors
        if event_type == "error":
            result.errors.append(event.get("message", str(event)))

    result.turn_count = turn_count
    return result


async def check_stall(
    ssh: SSHService,
    jsonl_path: str,
    stall_timeout_seconds: int = 600,
) -> bool:
    """Check if the stream-json file has been written to recently.

    Returns True if the file hasn't been modified for longer than
    ``stall_timeout_seconds``, indicating the agent may be stalled.
    """
    stdout, _, rc = await ssh.run_command(
        f"stat -c %Y {jsonl_path} 2>/dev/null",
        timeout=10,
    )
    if rc != 0 or not stdout.strip():
        return False  # File doesn't exist yet, not a stall

    try:
        mtime = int(stdout.strip())
    except ValueError:
        return False

    # Get remote server time
    now_stdout, _, now_rc = await ssh.run_command("date +%s", timeout=10)
    if now_rc != 0:
        return False

    try:
        now = int(now_stdout.strip())
    except ValueError:
        return False

    age = now - mtime
    return age > stall_timeout_seconds

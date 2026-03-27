# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Parse messaging commands into structured Command objects."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Command:
    """Parsed messaging command."""

    action: str  # run, status, approve, reject, list, talk, help
    project: str | None = None
    args: dict = field(default_factory=dict)
    raw_text: str = ""


def parse_command(text: str) -> Command:
    """Parse a command string into a Command object.

    Examples:
        "run myproject Fix the login bug" -> Command(action="run", project="myproject", args={"task": "Fix the login bug"})
        "status 42" -> Command(action="status", args={"run_id": "42"})
        "approve 42" -> Command(action="approve", args={"run_id": "42"})
        "reject 42 bad approach" -> Command(action="reject", args={"run_id": "42", "reason": "bad approach"})
        "list" -> Command(action="list")
        "talk sess-123 What did you change?" -> Command(action="talk", args={"session_id": "sess-123", "message": "What did you change?"})
        "help" -> Command(action="help")
    """
    text = text.strip()
    # Remove bot mention prefix if present
    text = re.sub(r"^<@[^>]+>\s*", "", text)
    text = re.sub(r"^/agentickode\s*", "", text, flags=re.IGNORECASE)

    parts = text.split(None, 2)
    if not parts:
        return Command(action="help", raw_text=text)

    action = parts[0].lower()

    if action == "run" and len(parts) >= 2:
        project = parts[1]
        task = parts[2] if len(parts) > 2 else ""
        return Command(action="run", project=project, args={"task": task}, raw_text=text)

    if action in ("status", "approve") and len(parts) >= 2:
        return Command(action=action, args={"run_id": parts[1]}, raw_text=text)

    if action == "reject" and len(parts) >= 2:
        run_id = parts[1]
        reason = parts[2] if len(parts) > 2 else ""
        return Command(action="reject", args={"run_id": run_id, "reason": reason}, raw_text=text)

    if action == "talk" and len(parts) >= 2:
        session_id = parts[1]
        message = parts[2] if len(parts) > 2 else ""
        return Command(
            action="talk", args={"session_id": session_id, "message": message}, raw_text=text
        )

    if action in ("list", "help"):
        return Command(action=action, raw_text=text)

    # Unknown command — treat entire text as a "run" task on default project
    return Command(action="help", raw_text=text)

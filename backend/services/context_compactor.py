# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Context compactor — summarizes completed episodes for session continuation.

Inspired by OpenClaw's compaction engine: extracts key decisions and file
changes from episode stream logs and git diffs to build compact continuation
prompts that fit within Claude's context window.
"""

from __future__ import annotations

import json
import logging
import shlex

from backend.services.workspace.command_executor import CommandExecutor

logger = logging.getLogger("agentickode.context_compactor")

# Max lines to extract from episode JSONL for summarization
_MAX_ASSISTANT_LINES = 30


class ContextCompactor:
    """Builds compact summaries of completed episodes."""

    def __init__(self, ssh: CommandExecutor, workspace: str):
        self._ssh = ssh
        self._workspace = workspace

    async def compact_episode(self, episode_num: int) -> str:
        """Build a summary from episode JSONL + git diff.

        Extracts:
        - Files created/modified (from git diff)
        - Recent commits
        - Key assistant messages from the JSONL stream
        """
        ws = shlex.quote(self._workspace)

        # Recent commits
        commits, _, _ = await self._ssh.run_command(
            f"cd {ws} && git log --oneline -5 2>/dev/null || echo '(no commits)'",
            timeout=15,
        )

        # Files changed
        files, _, _ = await self._ssh.run_command(
            f"cd {ws} && git diff --name-only HEAD~1 2>/dev/null || echo '(unknown)'",
            timeout=15,
        )

        # Extract key decisions from JSONL
        decisions = await self._extract_decisions(episode_num)

        parts = [
            f"## Episode {episode_num} Summary\n",
            f"### Recent commits\n{commits.strip()}\n",
            f"### Files changed\n{files.strip()}\n",
        ]
        if decisions:
            parts.append(f"### Key decisions\n{decisions}\n")

        return "\n".join(parts)

    async def build_continuation_prompt(
        self,
        task_description: str,
        episodes_summary: str,
        episode_num: int,
    ) -> str:
        """Build the full prompt for a continuation episode."""
        ws = shlex.quote(self._workspace)

        # Current state of the workspace
        status, _, _ = await self._ssh.run_command(
            f"cd {ws} && git status --short 2>/dev/null | head -20",
            timeout=15,
        )

        return (
            f"# Continuation — Episode {episode_num}\n\n"
            f"## Original task\n{task_description}\n\n"
            f"## What was accomplished\n{episodes_summary}\n\n"
            f"## Current workspace status\n```\n{status.strip()}\n```\n\n"
            f"## Instructions\n"
            f"Continue working on the original task. Review the current state "
            f"of the code and pick up where you left off. Focus on completing "
            f"remaining work items.\n"
        )

    async def _extract_decisions(self, episode_num: int) -> str:
        """Extract key assistant messages from episode JSONL."""
        ws = shlex.quote(self._workspace)
        jsonl_path = f"{ws}/.autodev/episode_{episode_num}.jsonl"

        stdout, _, rc = await self._ssh.run_command(
            f"cat {jsonl_path} 2>/dev/null | head -500",
            timeout=15,
        )
        if rc != 0 or not stdout.strip():
            return ""

        decisions: list[str] = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(event, dict):
                continue

            # Extract assistant messages that mention key actions
            if event.get("type") == "assistant":
                content = event.get("content", "")
                if isinstance(content, str) and len(content) > 50:
                    # Keep first 200 chars of substantial messages
                    decisions.append(f"- {content[:200]}...")

            if len(decisions) >= _MAX_ASSISTANT_LINES:
                break

        return "\n".join(decisions[-10:])  # Keep last 10 decisions

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Coding phase utilities: templates, prompt builders, and helper functions."""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.git import RemoteGitOps
from backend.worker.phases._helpers import get_ssh_for_run

logger = logging.getLogger("agentickode.phases.coding")

# ---------------------------------------------------------------------------
# Template constants
# ---------------------------------------------------------------------------

FALLBACK_SYSTEM_PROMPT = (
    "You are an expert software developer implementing code changes.\n\n"
    "IMPORTANT: You are running autonomously. Do NOT ask clarifying questions. "
    "Make your best judgment and implement the changes directly.\n\n"
    "Follow existing code patterns and style. Add appropriate error handling. "
    "Write or update tests if applicable. Commit changes with descriptive messages."
)

FALLBACK_USER_TEMPLATE = """## Subtask
{title}

## Description
{description}

## Files Likely Affected
{files}

## Previous Changes in This Session
{prev}

## Instructions
1. Implement the subtask as described — do NOT ask questions, just implement
2. Follow existing code patterns and style
3. Add appropriate error handling
4. Write or update tests if applicable
5. Commit changes with a descriptive message
6. If the task is ambiguous, use your best judgment and proceed"""

CONTINUATION_TEMPLATE = """## Next Subtask
{title}

## Description
{description}

## Files Likely Affected
{files}

Continue from where you left off. The previous changes are already in the workspace."""

BATCH_TEMPLATE = """## Task: {task_title}

You have {count} subtasks to implement. Complete ALL of them in order.
Commit after each subtask with a descriptive message.

{subtask_list}

## Instructions
1. Implement ALL subtasks in order — do NOT ask questions, just implement
2. Follow existing code patterns and style
3. Add appropriate error handling
4. Write or update tests if applicable
5. Commit changes after each subtask with a descriptive message
6. If a subtask is ambiguous, use your best judgment and proceed"""

CONSOLIDATED_TEMPLATE = """## Task
**{title}**

{description}

{context_section}

## Instructions
You are responsible for the FULL lifecycle of this task in a single pass:
1. **Analyze** the codebase to understand the relevant code and architecture
2. **Plan** your approach — decide what changes are needed and in what order
3. **Implement** all changes — follow existing code patterns and style
4. **Test** — run existing tests, fix any you break, add new tests if appropriate
5. **Self-review** — review your own diff for bugs, style issues, and missed edge cases
6. **Commit** your changes with descriptive commit message(s)

Do NOT ask clarifying questions — use your best judgment and proceed autonomously.
Do NOT leave TODOs or placeholders — complete everything to a working state."""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def build_coding_prompt(subtask: dict, previous_changes: list[str], template: str) -> str:
    """Build a full coding prompt for a subtask."""
    # Cap previous_changes to last 10 files to avoid unbounded token growth
    capped = previous_changes[-10:] if len(previous_changes) > 10 else previous_changes
    prev = "\n".join(capped) if capped else "None yet"
    if len(previous_changes) > 10:
        prev = f"[...{len(previous_changes) - 10} earlier files omitted]\n{prev}"
    files = ", ".join(subtask.get("files_likely_affected", []))
    return template.format(
        title=subtask.get("title", ""),
        description=subtask.get("description", ""),
        files=files,
        prev=prev,
    )


def build_continuation_prompt(subtask: dict) -> str:
    """Build a shorter prompt for session continuation.

    When an agent session is active, the agent already has full project context
    from the conversation history, so we send a minimal follow-up message.
    """
    title = subtask.get("title", "")
    desc = subtask.get("description", "")
    files = ", ".join(subtask.get("files_likely_affected", []))
    return CONTINUATION_TEMPLATE.format(title=title, description=desc, files=files)


def build_batch_prompt(subtasks: list[dict], task_title: str) -> str:
    """Combine all subtasks into a single prompt for batch execution."""
    parts: list[str] = []
    for i, st in enumerate(subtasks):
        title = st.get("title", f"Subtask {i + 1}")
        desc = st.get("description", "")
        files = ", ".join(st.get("files_likely_affected", []))
        part = f"### Subtask {i + 1}: {title}\n{desc}"
        if files:
            part += f"\nFiles: {files}"
        parts.append(part)

    subtask_list = "\n\n".join(parts)
    return BATCH_TEMPLATE.format(
        task_title=task_title,
        count=len(subtasks),
        subtask_list=subtask_list,
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


async def auto_commit_changes(
    task_run: TaskRun,
    session: AsyncSession,
    subtask_title: str,
    log_fn: Callable[..., Awaitable[None]],
) -> bool:
    """Check for uncommitted changes and auto-commit them.

    Returns True if a commit was made, False if workspace was clean.
    """
    workspace = task_run.workspace_path
    if not workspace:
        return False

    try:
        ssh = await get_ssh_for_run(task_run, session)
        remote_git = RemoteGitOps(ssh)

        # Mark directory safe (root running git in worker-owned dir)
        await remote_git._mark_safe_directory(workspace)

        # Check for uncommitted changes (staged + unstaged + untracked)
        status = await remote_git.run_git(["status", "--porcelain"], cwd=workspace)
        if not status.stdout or not status.stdout.strip():
            return False

        # Stage all changes and commit
        await remote_git.run_git(["add", "-A"], cwd=workspace)
        msg = f"feat: {subtask_title[:100]}"
        await remote_git.run_git(
            ["commit", "-m", msg, "--allow-empty-message"],
            cwd=workspace,
        )
        return True
    except Exception as e:
        logger.warning("Auto-commit failed for run #%d: %s", task_run.id, e)
        await log_fn(f"Auto-commit skipped: {e}")
        return False


def get_previous_session_id(task_run: TaskRun) -> str | None:
    """Check if a previous phase stored a session_id we can continue from.

    Currently checks the planning_result — if planning was done via the same
    session-capable agent, it may have stored a session_id.
    """
    planning = task_run.planning_result
    if planning and isinstance(planning, dict):
        sid = planning.get("session_id")
        if sid and isinstance(sid, str):
            return sid
    return None


def make_results(results: list, session_id: str | None = None) -> dict:
    """Build coding results dict, including session_id for cross-phase continuity."""
    data: dict = {"results": results}
    if session_id:
        data["session_id"] = session_id
    return data


def format_pr_comments(comments: list[dict]) -> str:
    """Format PR review comments into readable text for the coding agent."""
    lines: list[str] = []
    for c in comments:
        body = c.get("body", "").strip()
        if not body:
            continue
        path = c.get("path", "")
        line = c.get("line") or c.get("original_line")
        loc = f"`{path}:{line}`" if path and line else (f"`{path}`" if path else "")
        prefix = f"- {loc} " if loc else "- "
        lines.append(f"{prefix}{body}")
    return "\n".join(lines) if lines else "No actionable comments found."

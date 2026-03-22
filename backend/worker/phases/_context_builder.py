# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Context package builder for the autonomous agent loop.

Assembles .autodev/context.md and .autodev/agent_prompt.md in the workspace
before handing off to Claude Code for autonomous execution.
"""

from __future__ import annotations

import json
import logging
import shlex
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.services.workspace.ssh_service import SSHService
from backend.worker.phases._helpers import get_ssh_for_run

logger = logging.getLogger("agentickode.phases.context_builder")

# Maximum chars for RAG snippets (prevent bloating the prompt)
_MAX_RAG_CHARS = 8000

# Maximum lines for git history
_GIT_LOG_LINES = 20


async def build_context_package(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    *,
    autonomy_config: dict | None = None,
) -> str:
    """Build .autodev/context.md and .autodev/agent_prompt.md in the workspace.

    Returns a new session_id that can be used to resume the Claude session.
    """
    ssh = await get_ssh_for_run(task_run, session)
    workspace = task_run.workspace_path or ""
    config = autonomy_config or {}

    await _ensure_autodev_dir(ssh, workspace)

    git_history = await _get_git_history(ssh, workspace)
    project_structure = await _get_project_structure(ssh, workspace)
    test_status = await _get_test_status(ssh, workspace)
    rag_snippets = await _get_rag_snippets(task_run, services)

    context_md = _build_context_md(
        task_run=task_run,
        git_history=git_history,
        project_structure=project_structure,
        test_status=test_status,
        rag_snippets=rag_snippets,
    )

    autonomy_instructions = _build_autonomy_instructions(config)
    agent_prompt_md = _build_agent_prompt(task_run, autonomy_instructions)

    await _write_file(ssh, workspace, ".autodev/context.md", context_md)
    await _write_file(ssh, workspace, ".autodev/agent_prompt.md", agent_prompt_md)

    # Seed an empty progress file so the poller doesn't error on first read
    initial_progress = json.dumps(
        {"status": "starting", "message": "Agent initializing", "files_changed": []}
    )
    await _write_file(ssh, workspace, ".autodev/progress.json", initial_progress)

    session_id = str(uuid.uuid4())
    logger.info("Context package built for run #%s (session_id=%s)", task_run.id, session_id)
    return session_id


async def read_workspace_json(
    ssh: SSHService,
    workspace: str,
    relative_path: str,
) -> dict | list | None:
    """Read and parse a JSON file from the workspace. Returns None on any error."""
    stdout, _, rc = await ssh.run_command(f"cat {shlex.quote(f'{workspace}/{relative_path}')}")
    if rc != 0 or not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        logger.debug("Could not parse JSON from %s/%s", workspace, relative_path)
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _ensure_autodev_dir(ssh: SSHService, workspace: str) -> None:
    await ssh.run_command(f"mkdir -p {shlex.quote(workspace)}/.autodev")


async def _get_git_history(ssh: SSHService, workspace: str) -> str:
    stdout, _, rc = await ssh.run_command(
        f"cd {shlex.quote(workspace)} && git log --oneline -{_GIT_LOG_LINES} 2>/dev/null"
    )
    return stdout.strip() if rc == 0 else "(git history unavailable)"


async def _get_project_structure(ssh: SSHService, workspace: str) -> str:
    # Get a representative file listing — avoid huge outputs
    stdout, _, rc = await ssh.run_command(
        f"cd {shlex.quote(workspace)} && "
        "find . -type f \\( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' "
        "-o -name '*.go' -o -name '*.rs' -o -name '*.java' \\) "
        "-not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/dist/*' "
        "-not -path '*/__pycache__/*' -not -path '*/venv/*' "
        "2>/dev/null | sort | head -100"
    )
    return stdout.strip() if rc == 0 else "(project structure unavailable)"


async def _get_test_status(ssh: SSHService, workspace: str) -> str:
    """Try to get quick test collection status without running tests."""
    # Try pytest collect-only (Python) — non-destructive
    stdout, _, rc = await ssh.run_command(
        f"cd {shlex.quote(workspace)} && python -m pytest --co -q 2>&1 | tail -5",
        timeout=30,
    )
    if rc == 0 and stdout.strip():
        return stdout.strip()

    # Try jest --listTests (JS/TS)
    stdout, _, rc = await ssh.run_command(
        f"cd {shlex.quote(workspace)} && npx jest --listTests 2>&1 | head -10",
        timeout=20,
    )
    if rc == 0 and stdout.strip():
        return stdout.strip()

    return "(test status unavailable)"


async def _get_rag_snippets(task_run: TaskRun, services: ServiceContainer) -> str:
    """Query ChromaDB for relevant file snippets based on the task description."""
    if not services.chromadb:
        return ""
    try:
        results = await services.chromadb.query(
            query=task_run.description or task_run.title,
            project_id=task_run.project_id,
            n_results=10,
        )
        if not results:
            return ""
        snippets = []
        for doc in results[:10]:
            snippets.append(f"### {doc.get('source', 'file')}\n{doc.get('content', '')[:500]}")
        combined = "\n\n".join(snippets)
        return combined[:_MAX_RAG_CHARS]
    except Exception:
        logger.debug("RAG query failed for run #%s", task_run.id, exc_info=True)
        return ""


def _build_context_md(
    *,
    task_run: TaskRun,
    git_history: str,
    project_structure: str,
    test_status: str,
    rag_snippets: str,
) -> str:
    sections = [
        "# AutoDev Task Context",
        "",
        "## Task",
        f"**Title**: {task_run.title}",
        f"**Source**: {task_run.task_source}",
        f"**Project**: {task_run.project_id}",
        f"**Branch**: {task_run.branch_name}",
        "",
        "**Description**:",
        task_run.description or "(no description)",
        "",
        "## Recent Git History",
        "```",
        git_history,
        "```",
        "",
        "## Project File Structure",
        "```",
        project_structure,
        "```",
        "",
        "## Test Collection Status",
        "```",
        test_status,
        "```",
    ]

    if rag_snippets:
        sections += [
            "",
            "## Relevant Code Snippets (semantic search)",
            rag_snippets,
        ]

    return "\n".join(sections)


def _build_autonomy_instructions(config: dict) -> str:
    plan_approval = config.get("plan_approval", "none")
    allow_followups = config.get("allow_agent_followups", False)
    merge_mode = config.get("merge_mode", "pr_only")

    lines = ["## Constraints and Reporting Protocol", ""]

    if plan_approval in ("require_approval", "show_and_continue"):
        lines += [
            "**IMPORTANT**: Write your plan to `.autodev/plan.json` BEFORE making any code changes.",
            'Format: `{"steps": [...], "files_to_change": [...], "estimated_complexity": "..."}` ',
            "",
        ]

    lines += [
        "**Progress reporting**: Periodically write to `.autodev/progress.json`:",
        '`{"status": "exploring|planning|coding|testing|reviewing", "message": "...", "files_changed": [...]}`',
        "",
        "**When done**: Write your results to `.autodev/result.json`:",
        '`{"summary": "...", "files_changed": [...], "tests_passed": true|false, "pr_ready": true|false}`',
        "",
    ]

    if allow_followups:
        lines += [
            "**Follow-up tasks**: If you notice additional work needed (bugs, TODOs, coverage gaps),",
            "write them to `.autodev/follow_up_tasks.json`:",
            '`[{"title": "...", "description": "...", "priority": "high|medium|low"}]`',
            "",
        ]

    if merge_mode == "auto_merge":
        lines.append(
            "This project uses **auto-merge** — your changes will be merged automatically if CI passes."
        )
    else:
        lines.append("This project requires a **human PR review** before merging.")

    return "\n".join(lines)


def _build_agent_prompt(task_run: TaskRun, autonomy_instructions: str) -> str:
    return f"""# AutoDev Autonomous Task

## Your Task
{task_run.title}

{task_run.description or ''}

## Context
Read `.autodev/context.md` for full project context including git history, file structure, and relevant code snippets.

## Your Job
1. Read `.autodev/context.md` to understand the project
2. Explore the codebase as needed using your tools
3. Write your implementation plan to `.autodev/plan.json`
4. Execute the plan — write code, run tests, fix failures
5. Self-review your changes for quality and correctness
6. Write final results to `.autodev/result.json`
7. If you notice follow-up work, write it to `.autodev/follow_up_tasks.json`

{autonomy_instructions}

## Important
- Work in the current directory (workspace root)
- Commit your changes with descriptive commit messages as you go
- Run the test suite before declaring done
- Be thorough but focused — only change what's needed for this task
"""


async def _write_file(ssh: SSHService, workspace: str, relative_path: str, content: str) -> None:
    """Write content to a file in the workspace via SSH using a heredoc."""
    full_path = f"{workspace}/{relative_path}"
    # Use printf with base64 to avoid heredoc quoting issues with special chars
    import base64

    encoded = base64.b64encode(content.encode()).decode()
    cmd = f"echo {shlex.quote(encoded)} | base64 -d > {shlex.quote(full_path)}"
    _, stderr, rc = await ssh.run_command(cmd)
    if rc != 0:
        logger.warning("Failed to write %s: %s", relative_path, stderr)

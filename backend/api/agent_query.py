# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent query API — communicate with running task run agent sessions.

Sends prompts to workspace agents via --resume and returns structured
responses. Enables agent-to-agent communication through the platform.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models import AgentLoopExecution, TaskRun
from backend.models.servers import WorkspaceServer
from backend.services.workspace.ssh_service import SSHService

router = APIRouter(tags=["agent-query"])


_MAX_QUERY_TIMEOUT = 300


class QueryRequest(BaseModel):
    question: str
    timeout: int = 120


class RunAndWaitRequest(BaseModel):
    project_id: str
    title: str
    description: str = ""
    execution_mode: str | None = None
    timeout: int = 3600


@router.post("/runs/{run_id}/agent/query")
async def query_run_agent(run_id: int, req: QueryRequest):
    """Send a question to a run's agent session and get the response.

    Uses --resume {session_id} to continue the agent's conversation,
    so the agent has full context of what it did during the run.
    """
    async with async_session() as db:
        run = await db.get(TaskRun, run_id)
        if not run:
            raise HTTPException(404, "Run not found")

        # Get session ID from agent loop execution or coding results
        session_id = await _get_session_id(db, run)
        if not session_id:
            raise HTTPException(400, "No agent session found for this run")

        # Cap timeout to prevent abuse
        timeout = min(req.timeout, _MAX_QUERY_TIMEOUT)

        # Get workspace server + SSH
        try:
            ssh, workspace, worker_user = await _get_ssh_context(db, run)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(500, f"SSH connection failed: {exc}") from exc

        # Write question to temp file on remote (avoids shell escaping issues)
        q_path = f"{workspace}/.autodev/query_prompt.txt"
        escaped = req.question.replace("'", "'\\''")
        _, _, write_rc = await ssh.run_command(
            f"mkdir -p {shlex.quote(workspace)}/.autodev && "
            f"echo '{escaped}' > {shlex.quote(q_path)}",
            timeout=10,
        )
        if write_rc != 0:
            raise HTTPException(500, "Failed to write question to workspace")

        # Build --resume command
        cmd = (
            f"cd {shlex.quote(workspace)} && "
            f"cat {shlex.quote(q_path)} | "
            f"claude --print --output-format json --resume {session_id}"
        )

        # Wrap for non-root if needed
        if ssh.username == "root" and worker_user:
            user_path = (
                f"/home/{worker_user}/.local/bin"
                f":/home/{worker_user}/.claude/bin"
                ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            )
            inner = f"export PATH={shlex.quote(user_path)} && {cmd}"
            cmd = f"runuser -u {worker_user} -- bash -c {shlex.quote(inner)}"

        # Execute and wait for response
        try:
            stdout, stderr, rc = await ssh.run_command(cmd, timeout=timeout)
        except Exception as exc:
            return {
                "response": "",
                "exit_code": -1,
                "session_id": session_id,
                "error": f"SSH command failed: {exc}",
            }

        # Parse JSON output
        response_text = stdout.strip()
        parse_error = False
        try:
            data = json.loads(response_text)
            if isinstance(data, dict):
                response_text = data.get("result", data.get("content", response_text))
        except json.JSONDecodeError:
            parse_error = True

        error_msg = None
        if rc != 0:
            error_msg = stderr.strip()[:500] if stderr else f"Agent exited with code {rc}"

        return {
            "response": response_text,
            "exit_code": rc,
            "session_id": session_id,
            "error": error_msg,
            "parse_error": parse_error,
        }


@router.get("/runs/{run_id}/agent/diff")
async def get_run_diff(run_id: int):
    """Get the git diff of changes made by the agent in this run."""
    async with async_session() as db:
        run = await db.get(TaskRun, run_id)
        if not run:
            raise HTTPException(404, "Run not found")

        ssh, workspace, worker_user = await _get_ssh_context(db, run)
        ws = shlex.quote(workspace)

        # Get diff from the branch
        diff_out, _, _ = await ssh.run_command(
            f"cd {ws} && git diff HEAD~5 --stat 2>/dev/null || git diff --stat 2>/dev/null",
            timeout=15,
        )
        full_diff, _, _ = await ssh.run_command(
            f"cd {ws} && git diff HEAD~5 2>/dev/null | head -500 || git diff 2>/dev/null | head -500",
            timeout=15,
        )

        return {
            "summary": diff_out.strip(),
            "diff": full_diff.strip(),
        }


@router.get("/runs/{run_id}/agent/plan")
async def get_run_plan(run_id: int):
    """Get the agent's current plan from .autodev/plan.json."""
    async with async_session() as db:
        run = await db.get(TaskRun, run_id)
        if not run:
            raise HTTPException(404, "Run not found")

        # Try DB first
        if run.agent_plan:
            return {"plan": run.agent_plan, "source": "database"}

        # Try reading from workspace
        ssh, workspace, _ = await _get_ssh_context(db, run)
        ws = shlex.quote(workspace)
        stdout, _, rc = await ssh.run_command(
            f"cat {ws}/.autodev/plan.json 2>/dev/null",
            timeout=10,
        )
        if rc == 0 and stdout.strip():
            try:
                return {"plan": json.loads(stdout), "source": "workspace"}
            except json.JSONDecodeError:
                return {"plan": stdout.strip(), "source": "workspace_raw"}

        return {"plan": None, "source": "not_found"}


@router.post("/runs/create-and-wait")
async def create_run_and_wait(req: RunAndWaitRequest):
    """Create a task run and wait for it to complete.

    Polls the run status until completed/failed or timeout. Returns
    the final result including PR URL if created.
    """
    import httpx

    from backend.mcp.tools.projects import _BASE_URL

    # Create the run
    async with httpx.AsyncClient(timeout=30) as client:
        create_resp = await client.post(
            f"{_BASE_URL}/api/runs",
            json={
                "project_id": req.project_id,
                "title": req.title,
                "description": req.description,
                **({"execution_mode": req.execution_mode} if req.execution_mode else {}),
            },
        )
        create_resp.raise_for_status()
        run_data = create_resp.json()
        run_id = run_data.get("id")

    if not run_id:
        raise HTTPException(500, "Failed to create run")

    # Poll until done with exponential backoff
    deadline = time.monotonic() + req.timeout
    poll_interval = 5
    while time.monotonic() < deadline:
        await asyncio.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 30)  # 5s → 7.5s → 11s → ... → max 30s

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{_BASE_URL}/api/runs/{run_id}")
                resp.raise_for_status()
                run = resp.json()
        except Exception:
            continue  # Transient error, keep polling

        status = run.get("status", "")
        if status in ("completed", "failed", "cancelled"):
            return {
                "run_id": run_id,
                "status": status,
                "pr_url": run.get("pr_url"),
                "coding_results": run.get("coding_results"),
                "title": run.get("title"),
            }

    return {
        "run_id": run_id,
        "status": "timeout",
        "message": f"Run #{run_id} did not complete within {req.timeout}s",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_session_id(db: AsyncSession, run: TaskRun) -> str | None:
    """Get the agent session ID for a run."""
    # Check agent_loop_executions
    result = await db.execute(
        select(AgentLoopExecution)
        .where(AgentLoopExecution.task_run_id == run.id)
        .order_by(AgentLoopExecution.id.desc())
        .limit(1)
    )
    ale = result.scalar_one_or_none()
    if ale and ale.session_id:
        return str(ale.session_id)

    # Check coding_results
    if isinstance(run.coding_results, dict):
        sid = run.coding_results.get("session_id")
        if sid:
            return sid

    return None


async def _get_ssh_context(db: AsyncSession, run: TaskRun) -> tuple[SSHService, str, str | None]:
    """Get SSH service, workspace path, and worker user for a run."""
    if not run.workspace_server_id:
        raise HTTPException(400, "Run has no workspace server")

    server = await db.get(WorkspaceServer, run.workspace_server_id)
    if not server:
        raise HTTPException(404, "Workspace server not found")

    ssh = SSHService.for_server(server)
    workspace = str(run.workspace_path or "")
    worker_user = str(server.worker_user) if server.worker_user else None

    return ssh, workspace, worker_user

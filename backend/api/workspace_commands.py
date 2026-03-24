# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace command execution API — run commands on remote workspace servers."""

from __future__ import annotations

import shlex

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import async_session
from backend.models.servers import WorkspaceServer
from backend.services.workspace.ssh_service import SSHService

router = APIRouter(tags=["workspace-commands"])


class ExecRequest(BaseModel):
    command: str
    timeout: int = 30
    user: str | None = None


@router.post("/workspace-servers/{server_id}/exec")
async def exec_command(server_id: int, req: ExecRequest):
    """Execute a shell command on a workspace server via SSH."""
    ssh = await _get_ssh(server_id)

    if req.user:
        cmd = f"runuser -u {shlex.quote(req.user)} -- bash -c {shlex.quote(req.command)}"
    else:
        cmd = req.command

    stdout, stderr, rc = await ssh.run_command(cmd, timeout=req.timeout)

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": rc,
    }


@router.get("/workspace-servers/{server_id}/read-file")
async def read_file(server_id: int, path: str):
    """Read a file from a workspace server."""
    ssh = await _get_ssh(server_id)
    stdout, stderr, rc = await ssh.run_command(
        f"cat {shlex.quote(path)} 2>/dev/null",
        timeout=15,
    )
    if rc != 0:
        raise HTTPException(404, f"File not found or not readable: {path}")
    return {"content": stdout, "path": path}


@router.get("/workspace-servers/{server_id}/ls")
async def list_directory(server_id: int, path: str = "/"):
    """List files in a directory on a workspace server."""
    ssh = await _get_ssh(server_id)
    stdout, stderr, rc = await ssh.run_command(
        f"ls -la {shlex.quote(path)} 2>/dev/null",
        timeout=15,
    )
    if rc != 0:
        raise HTTPException(404, f"Directory not found: {path}")
    return {"listing": stdout, "path": path}


async def _get_ssh(server_id: int) -> SSHService:
    async with async_session() as db:
        server = await db.get(WorkspaceServer, server_id)
    if not server:
        raise HTTPException(404, f"Server #{server_id} not found")
    return SSHService.for_server(server)

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent setup API — check and run post-install for local agents."""

from __future__ import annotations

import asyncio
import os
import shutil

from fastapi import APIRouter

router = APIRouter(tags=["agent-setup"])

_PATH = f"/root/.local/bin:/root/.local/share/claude/bin:{os.environ.get('PATH', '')}"


@router.get("/agent-setup/status")
async def get_setup_status():
    """Check which agents and plugins are installed locally."""
    agents: dict[str, dict] = {}

    for name in ("claude", "codex", "gemini", "aider", "opencode"):
        installed = shutil.which(name) is not None
        agents[name] = {"installed": installed, "path": shutil.which(name)}

    # Check Claude-specific extras
    claude_extras: dict[str, bool] = {}
    if agents.get("claude", {}).get("installed"):
        # Check if MCP server registered
        proc = await asyncio.create_subprocess_shell(
            f'export PATH="{_PATH}" && claude mcp list 2>/dev/null | grep -q agentickode',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        claude_extras["mcp_agentickode"] = proc.returncode == 0

        # Check if plugins installed (check for a known plugin)
        proc = await asyncio.create_subprocess_shell(
            f'export PATH="{_PATH}" && claude plugin list 2>/dev/null | head -5',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        plugin_count = len([line for line in stdout.decode().strip().split("\n") if line.strip()])
        claude_extras["plugins_installed"] = plugin_count > 0
        claude_extras["plugin_count"] = plugin_count

        # Check superclaude
        claude_extras["superclaude"] = shutil.which("superclaude") is not None

        # Check GSD
        proc = await asyncio.create_subprocess_shell(
            f'export PATH="{_PATH}" && npx get-shit-done-cc --version 2>/dev/null',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        claude_extras["gsd"] = proc.returncode == 0

    needs_setup = (
        not all(
            [
                claude_extras.get("mcp_agentickode", False),
                claude_extras.get("plugins_installed", False),
            ]
        )
        if agents.get("claude", {}).get("installed")
        else False
    )

    return {
        "agents": agents,
        "claude_extras": claude_extras,
        "needs_setup": needs_setup,
    }


@router.post("/agent-setup/run-post-install")
async def run_post_install():
    """Run the Claude post-install (plugins, marketplaces, MCP, skills)."""
    from backend.seed.agent_settings import _CLAUDE_POST_INSTALL_CMD

    cmd = f'export PATH="{_PATH}" && {_CLAUDE_POST_INSTALL_CMD}'

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)

    return {
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[-2000:],
        "stderr": stderr.decode("utf-8", errors="replace")[-1000:],
    }

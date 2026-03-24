# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent process manager — spawns and manages local AI agent processes."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field

logger = logging.getLogger("agentickode.chat.agent_process")

# System prompt for the conversational agent
_SYSTEM_PROMPT = """\
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

# Agent command configurations
AGENT_CONFIGS: dict[str, dict[str, list[str]]] = {
    "claude": {
        "cmd": ["claude", "--print", "--output-format", "stream-json"],
    },
    "opencode": {
        "cmd": ["opencode"],
    },
    "gemini": {
        "cmd": ["gemini"],
    },
    "aider": {
        "cmd": ["aider", "--yes", "--no-git"],
    },
}


@dataclass
class AgentProcess:
    """A running agent process with stdin/stdout pipes."""

    process: asyncio.subprocess.Process
    agent_name: str
    mcp_config_path: str
    _output_lines: list[str] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return self.process.returncode is None

    async def send(self, message: str) -> None:
        """Send a message to the agent's stdin."""
        if not self.alive or not self.process.stdin:
            return
        self.process.stdin.write(f"{message}\n".encode())
        await self.process.stdin.drain()

    async def read_output(self, timeout: float = 30.0) -> str:
        """Read output from stdout until timeout or completion."""
        if not self.process.stdout:
            return ""
        chunks: list[str] = []
        try:
            while True:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=timeout)
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                chunks.append(decoded)
                self._output_lines.append(decoded)
                # Check for completion signals in stream-json
                try:
                    event = json.loads(decoded)
                    if isinstance(event, dict) and event.get("type") == "result":
                        break
                except json.JSONDecodeError:
                    pass
        except TimeoutError:
            pass
        return "\n".join(chunks)

    async def kill(self) -> None:
        """Kill the agent process."""
        if self.alive:
            self.process.kill()
            await self.process.wait()
        # Clean up MCP config
        if os.path.exists(self.mcp_config_path):
            os.unlink(self.mcp_config_path)


async def spawn_agent(
    agent_name: str,
    platform_url: str = "http://localhost:8000",
) -> AgentProcess:
    """Spawn a local agent process with MCP server configured.

    Uses create_subprocess_exec (not shell) to avoid command injection.

    Args:
        agent_name: Agent to spawn (claude, opencode, gemini, aider)
        platform_url: Platform API URL for MCP tools

    Returns:
        AgentProcess with stdin/stdout pipes
    """
    config = AGENT_CONFIGS.get(agent_name)
    if not config:
        msg = f"Unknown agent: {agent_name}. Available: {list(AGENT_CONFIGS.keys())}"
        raise ValueError(msg)

    # Check agent is installed
    cmd_name = config["cmd"][0]
    if not shutil.which(cmd_name):
        msg = f"Agent {cmd_name} not found in PATH"
        raise FileNotFoundError(msg)

    # Write MCP config for the agent
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

    # Build command with MCP config — uses exec, not shell
    cmd = list(config["cmd"])
    if agent_name == "claude":
        cmd.extend(["--mcp-config", config_path])

    env = {**os.environ, "AGENTICKODE_URL": platform_url}

    logger.info("Spawning %s: %s", agent_name, " ".join(cmd))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    return AgentProcess(
        process=process,
        agent_name=agent_name,
        mcp_config_path=config_path,
    )


def get_system_prompt() -> str:
    """Return the system prompt for the conversational agent."""
    return _SYSTEM_PROMPT

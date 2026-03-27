# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent relay — bridge between messaging platforms and running agent sessions.

Sends messages to remote agents via tmux and captures their responses.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sessions import CliSession
from backend.services.workspace.ssh_service import SSHService

logger = logging.getLogger("agentickode.messaging.agent_relay")


class AgentRelay:
    """Bridge messaging platform messages to running agent tmux sessions."""

    async def relay_to_agent(self, session_id: str, message: str, db_session: AsyncSession) -> str:
        """Send a message to a running agent and capture its response.

        Args:
            session_id: The CLI session ID.
            message: The message to send to the agent.
            db_session: Database session for looking up CLI session details.

        Returns:
            The captured agent output (last 30 lines of tmux pane).
        """
        result = await db_session.execute(
            select(CliSession).where(CliSession.session_id == session_id)
        )
        cli_session = result.scalar_one_or_none()
        if not cli_session:
            return f"Session `{session_id}` not found."

        if cli_session.status != "active":
            return f"Session `{session_id}` is {cli_session.status}, not active."

        # Get workspace server for SSH connection
        from backend.models.servers import WorkspaceServer

        server_result = await db_session.execute(
            select(WorkspaceServer).where(WorkspaceServer.id == cli_session.workspace_server_id)
        )
        server = server_result.scalar_one_or_none()
        if not server:
            return "Workspace server not found for this session."

        try:
            ssh = SSHService(
                hostname=server.hostname,
                port=server.port or 22,
                username=server.username or "root",
                key_path=server.ssh_key_path,
            )

            # Escape message for tmux
            escaped = message.replace("'", "'\\''")
            tmux_name = cli_session.tmux_session

            # Send message to tmux pane
            await ssh.run_command(
                f"tmux send-keys -t {tmux_name} '{escaped}' Enter",
                timeout=10,
            )

            # Wait a moment for agent to process
            import asyncio

            await asyncio.sleep(3)

            # Capture output
            stdout, _, exit_code = await ssh.run_command(
                f"tmux capture-pane -t {tmux_name} -p -S -30",
                timeout=10,
            )

            return stdout.strip() if stdout else "(no output captured)"

        except Exception as e:
            logger.exception("Failed to relay message to session %s", session_id)
            return f"Error relaying to agent: {e}"

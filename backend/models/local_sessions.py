# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""LocalTerminalSession model for persistent local agent terminal sessions."""

from sqlalchemy import Column, DateTime, Integer, Text, func

from backend.models.base import Base


class LocalTerminalSession(Base):
    __tablename__ = "local_terminal_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, unique=True, nullable=False)
    agent_name = Column(Text, nullable=False)
    tmux_name = Column(Text, unique=True, nullable=False)
    display_name = Column(Text, nullable=True)
    last_command = Column(Text, nullable=True)
    agent_session_id = Column(Text, nullable=True)  # Claude --session-id for --resume
    run_as_user = Column(Text, nullable=True)  # OS user the tmux session runs as (null = root)
    status = Column(Text, nullable=False, default="active")  # active, closed
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_activity_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)

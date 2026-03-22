# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""CliSession model for persistent CLI agent sessions."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from backend.models.base import Base


class CliSession(Base):
    __tablename__ = "cli_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, unique=True, nullable=False)
    workspace_server_id = Column(
        Integer, ForeignKey("workspace_servers.id", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        Text, ForeignKey("project_configs.project_id", ondelete="SET NULL"), nullable=True
    )
    task_run_id = Column(Integer, ForeignKey("task_runs.id", ondelete="SET NULL"), nullable=True)
    agent_name = Column(Text, nullable=False)
    user_context = Column(Text, nullable=False, default="coder")
    workspace_path = Column(Text, nullable=True)
    display_name = Column(Text, nullable=True)
    tmux_session = Column(Text, nullable=False)
    pid = Column(Integer, nullable=True)
    status = Column(Text, nullable=False, default="starting")
    remote_control_enabled = Column(Boolean, nullable=False, default=False)
    remote_control_port = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_activity_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    workspace_server = relationship("WorkspaceServer")
    project = relationship("ProjectConfig")
    task_run = relationship("TaskRun")

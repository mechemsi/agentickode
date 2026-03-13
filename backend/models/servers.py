# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from backend.models.base import Base


class WorkspaceServer(Base):
    __tablename__ = "workspace_servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    hostname = Column(Text, nullable=False)
    port = Column(Integer, nullable=False, default=22)
    username = Column(Text, nullable=False, default="root")
    ssh_key_path = Column(Text, nullable=True)
    workspace_root = Column(Text, nullable=False, default="/workspaces")
    status = Column(Text, nullable=False, default="unknown")
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    worker_user = Column(Text, nullable=True)
    worker_user_status = Column(Text, nullable=True)
    worker_user_error = Column(Text, nullable=True)
    worker_user_password = Column(Text, nullable=True)
    setup_log = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    agents = relationship(
        "DiscoveredAgent", back_populates="workspace_server", cascade="all, delete-orphan"
    )
    projects = relationship("ProjectConfig", back_populates="workspace_server")


class DiscoveredAgent(Base):
    __tablename__ = "discovered_agents"
    __table_args__ = (
        UniqueConstraint(
            "workspace_server_id", "agent_name", "user_context", name="uq_server_agent_ctx"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_server_id = Column(
        Integer, ForeignKey("workspace_servers.id", ondelete="CASCADE"), nullable=False
    )
    agent_name = Column(Text, nullable=False)
    user_context = Column(String(20), nullable=False, server_default="admin")
    agent_type = Column(Text, nullable=False)
    path = Column(Text, nullable=True)
    version = Column(Text, nullable=True)
    available = Column(Boolean, nullable=False, default=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    discovered_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    workspace_server = relationship("WorkspaceServer", back_populates="agents")

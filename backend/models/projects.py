# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from backend.models.base import Base


class ProjectConfig(Base):
    __tablename__ = "project_configs"

    project_id = Column(Text, primary_key=True)
    project_slug = Column(Text, nullable=False)
    repo_owner = Column(Text, nullable=False)
    repo_name = Column(Text, nullable=False)
    default_branch = Column(Text, nullable=False, default="main")
    task_source = Column(Text, nullable=False, default="plane")
    git_provider = Column(Text, nullable=False, default="gitea")
    workspace_config = Column(JSONB, nullable=True)
    ai_config = Column(JSONB, nullable=True)
    workspace_path = Column(Text, nullable=True)
    git_provider_token_enc = Column(Text, nullable=True)
    autonomy_config = Column(JSONB, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    runs = relationship("TaskRun", back_populates="project")
    workspace_servers = relationship(
        "ProjectWorkspaceServer",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectWorkspaceServer.priority",
    )
    scheduled_tasks = relationship("ScheduledTask", back_populates="project", cascade="all, delete-orphan")
    monitoring_rules = relationship("MonitoringRule", back_populates="project", cascade="all, delete-orphan")
    notification_sources = relationship("NotificationSource", back_populates="project", cascade="all, delete-orphan")


class ProjectWorkspaceServer(Base):
    __tablename__ = "project_workspace_servers"

    project_id = Column(Text, ForeignKey("project_configs.project_id", ondelete="CASCADE"), primary_key=True)
    workspace_server_id = Column(Integer, ForeignKey("workspace_servers.id", ondelete="CASCADE"), primary_key=True)
    priority = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    project = relationship("ProjectConfig", back_populates="workspace_servers")
    workspace_server = relationship("WorkspaceServer", back_populates="project_workspace_servers")

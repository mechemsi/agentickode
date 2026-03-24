# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""WorkspaceReadiness model — tracks dev-toolchain validation per (project, server)."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from backend.models.base import Base


class WorkspaceReadiness(Base):
    __tablename__ = "workspace_readiness"
    __table_args__ = (
        UniqueConstraint("project_id", "workspace_server_id", name="uq_readiness_proj_srv"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Text, ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=False
    )
    workspace_server_id = Column(
        Integer, ForeignKey("workspace_servers.id", ondelete="CASCADE"), nullable=False
    )
    validation_status = Column(Text, nullable=False, default="pending")
    validated_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    check_results = Column(JSONB, nullable=True)
    validation_report = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project = relationship("ProjectConfig")
    workspace_server = relationship("WorkspaceServer")

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from backend.models.base import Base


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        UniqueConstraint("role", "workspace_server_id", "priority", name="uq_role_scope_priority"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(Text, nullable=False)  # planner / coder / reviewer / fast
    provider_type = Column(Text, nullable=False)  # ollama / agent
    ollama_server_id = Column(Integer, ForeignKey("ollama_servers.id"), nullable=True)
    model_name = Column(Text, nullable=True)  # Ollama model name
    agent_name = Column(Text, nullable=True)  # claude / codex / opencode / aider / openhands
    workspace_server_id = Column(
        Integer, ForeignKey("workspace_servers.id"), nullable=True
    )  # null = global default
    priority = Column(Integer, nullable=False, default=0)  # 0 = primary, 1 = fallback
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    ollama_server = relationship(
        "OllamaServer", back_populates="role_assignments", foreign_keys=[ollama_server_id]
    )
    workspace_server = relationship("WorkspaceServer", foreign_keys=[workspace_server_id])

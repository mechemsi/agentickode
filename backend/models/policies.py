# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Agent policy model for safety and budget controls."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from backend.models.base import Base


class AgentPolicy(Base):
    __tablename__ = "agent_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Text,
        ForeignKey("project_configs.project_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    max_budget_usd = Column(Float, nullable=True)
    max_turns_per_episode = Column(Integer, nullable=False, default=30)
    max_episodes = Column(Integer, nullable=False, default=5)
    max_total_duration_seconds = Column(Integer, nullable=False, default=7200)
    stall_timeout_seconds = Column(Integer, nullable=False, default=600)
    max_files_changed = Column(Integer, nullable=True)
    allowed_file_patterns = Column(JSONB, nullable=False, default=list)
    denied_file_patterns = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project = relationship("ProjectConfig", back_populates="agent_policy")

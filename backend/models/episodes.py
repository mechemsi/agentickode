# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Episode model for tracking bounded autonomous agent execution episodes."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import relationship

from backend.models.base import Base


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_loop_execution_id = Column(
        Integer,
        ForeignKey("agent_loop_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    episode_number = Column(Integer, nullable=False)
    session_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="running")
    git_checkpoint_sha = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    turn_count = Column(Integer, nullable=False, default=0)
    tokens_used = Column(Integer, nullable=False, default=0)
    context_usage_pct = Column(Float, nullable=False, default=0.0)
    stall_detected_at = Column(DateTime(timezone=True), nullable=True)
    summary = Column(Text, nullable=True)
    exit_code = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    agent_loop_execution = relationship("AgentLoopExecution", back_populates="episodes")

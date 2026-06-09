# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""FlowPrompt model — a single-agent-call run definition (ADR-009).

A flow prompt replaces the multi-step workflow template: a named prompt plus the
data the platform fetches for it. Each ``flow_type`` has a fixed set of data
sources (see ``backend/worker/flow/data_sources.py``); ``extra_data_sources``
lets a prompt declare additional ones.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from backend.models.base import Base


class FlowPrompt(Base):
    __tablename__ = "flow_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    # flow_type drives the fixed data fetch + agent mode, e.g. "implement", "pr_review".
    flow_type = Column(Text, nullable=False, default="implement")
    prompt = Column(Text, nullable=False)
    agent = Column(Text, nullable=True)  # null = project/global default agent
    # "task" (run in a checked-out workspace) or "generate" (diff-only, no checkout).
    agent_mode = Column(Text, nullable=False, default="task")
    extra_data_sources = Column(JSONB, nullable=True)  # list[str] declared on top of fixed
    triggers = Column(JSONB, nullable=True)  # label/PR/schedule routing (used in later phases)
    is_system = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""PlatformCron model — scheduled prompts sent to local agent terminal sessions."""

from sqlalchemy import Boolean, Column, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from backend.models.base import Base


class PlatformCron(Base):
    __tablename__ = "platform_crons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)

    # Cron schedule (5-field: "*/30 * * * *")
    schedule = Column(Text, nullable=False)

    # What to send when cron fires
    prompt = Column(Text, nullable=False)

    # Which session to send it to (ties to local_terminal_sessions.session_id)
    session_id = Column(Text, nullable=True)
    # If session is closed, auto-resume with this agent
    agent_name = Column(Text, nullable=False, default="claude")

    # Execution tracking
    enabled = Column(Boolean, nullable=False, default=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_result = Column(Text, nullable=True)  # success, error, session_not_found
    run_count = Column(Integer, nullable=False, default=0)

    # History of recent executions
    execution_log = Column(JSONB, nullable=False, default=list)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

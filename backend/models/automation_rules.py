# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""AutomationRule model — configurable event-driven dispatch rules."""

from sqlalchemy import Boolean, Column, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from backend.models.base import Base


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Text, nullable=True)  # nullable = global rule
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)

    # What triggers this rule
    event_source = Column(Text, nullable=False)  # run_event, webhook, monitoring, schedule
    event_filter = Column(JSONB, nullable=False, default=dict)  # match conditions

    # What happens when triggered
    action_type = Column(Text, nullable=False)  # create_run, notify, send_message
    action_config = Column(JSONB, nullable=False, default=dict)  # action parameters

    # Rate limiting
    cooldown_seconds = Column(Integer, nullable=False, default=300)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    trigger_count = Column(Integer, nullable=False, default=0)

    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

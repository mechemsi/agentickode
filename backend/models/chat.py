# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Chat session model for persistent conversational agent sessions."""

from sqlalchemy import Column, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from backend.models.base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=False, unique=True)
    user_id = Column(Text, nullable=False, default="default")
    agent_name = Column(Text, nullable=False, default="claude")
    display_name = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="active")
    messages = Column(JSONB, nullable=False, default=list)
    agent_session_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_activity_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

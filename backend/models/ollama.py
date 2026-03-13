# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from sqlalchemy import Column, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from backend.models.base import Base


class OllamaServer(Base):
    __tablename__ = "ollama_servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    url = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="unknown")
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    cached_models = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    role_assignments = relationship(
        "RoleAssignment",
        back_populates="ollama_server",
        foreign_keys="RoleAssignment.ollama_server_id",
    )

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from sqlalchemy import Column, DateTime, Integer, Text, func
from sqlalchemy.orm import relationship

from backend.models.base import Base


class ServerGroup(Base):
    __tablename__ = "server_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    git_token_encrypted = Column(Text, nullable=True)
    git_provider_type = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    servers = relationship("WorkspaceServer", back_populates="server_group")

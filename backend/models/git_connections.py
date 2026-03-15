# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""GitConnection model — stores encrypted git provider tokens with scope."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, func

from backend.models.base import Base


class GitConnection(Base):
    __tablename__ = "git_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    provider = Column(Text, nullable=False)  # github/gitea/gitlab/bitbucket
    base_url = Column(Text, nullable=True)  # for self-hosted instances
    token_enc = Column(Text, nullable=False)  # Fernet encrypted
    scope = Column(Text, nullable=False, default="global")  # global/server/project
    workspace_server_id = Column(
        Integer, ForeignKey("workspace_servers.id", ondelete="CASCADE"), nullable=True
    )
    project_id = Column(
        Text, ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=True
    )
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

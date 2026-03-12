# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from backend.models.base import Base


class ProjectInstruction(Base):
    __tablename__ = "project_instructions"
    __table_args__ = (UniqueConstraint("project_id", "phase_name", name="uq_project_phase"),)

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Text, ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=False
    )
    phase_name = Column(Text, nullable=False, default="__global__")
    content = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    versions = relationship(
        "ProjectInstructionVersion", back_populates="instruction", cascade="all, delete-orphan"
    )


class ProjectSecret(Base):
    __tablename__ = "project_secrets"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_secret_name"),)

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Text, ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=False
    )
    name = Column(Text, nullable=False)
    encrypted_value = Column(Text, nullable=False)
    inject_as = Column(Text, nullable=False, default="env_var")
    phase_scope = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProjectInstructionVersion(Base):
    __tablename__ = "project_instruction_versions"

    id = Column(Integer, primary_key=True)
    instruction_id = Column(
        Integer, ForeignKey("project_instructions.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(Text, nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    change_summary = Column(Text, nullable=True)

    instruction = relationship("ProjectInstruction", back_populates="versions")
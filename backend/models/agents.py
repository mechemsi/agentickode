# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from backend.models.base import Base


class RoleConfig(Base):
    __tablename__ = "role_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(Text, unique=True, nullable=False)
    display_name = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    system_prompt = Column(Text, nullable=False, default="")
    user_prompt_template = Column(Text, nullable=False, default="")
    phase_binding = Column(Text, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False)
    default_temperature = Column(Float, nullable=False, default=0.3)
    default_num_predict = Column(Integer, nullable=False, default=2048)
    extra_params = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    prompt_overrides = relationship(
        "RolePromptOverride", back_populates="role_config", cascade="all, delete-orphan"
    )


class RolePromptOverride(Base):
    __tablename__ = "role_prompt_overrides"
    __table_args__ = (UniqueConstraint("role_config_id", "cli_agent_name", name="uq_config_agent"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_config_id = Column(
        Integer, ForeignKey("role_configs.id", ondelete="CASCADE"), nullable=False
    )
    cli_agent_name = Column(
        Text, nullable=False
    )  # "claude", "codex", "gemini", "kimi", "aider", "opencode"
    system_prompt = Column(Text, nullable=True)  # null = fall back to RoleConfig.system_prompt
    user_prompt_template = Column(
        Text, nullable=True
    )  # null = fall back to RoleConfig.user_prompt_template
    minimal_mode = Column(
        Boolean, nullable=False, default=False
    )  # if true, skip system prompt entirely
    extra_params = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    role_config = relationship("RoleConfig", back_populates="prompt_overrides")


class AgentSettings(Base):
    __tablename__ = "agent_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(Text, unique=True, nullable=False)  # "claude", "codex", "gemini", etc.
    display_name = Column(Text, nullable=False)  # "Claude CLI", "OpenAI Codex", etc.
    description = Column(Text, nullable=False, default="")
    supports_session = Column(Boolean, nullable=False, default=False)
    default_timeout = Column(Integer, nullable=False, default=600)  # seconds
    max_retries = Column(Integer, nullable=False, default=1)
    environment_vars = Column(
        JSONB, nullable=False, default=dict
    )  # {"ANTHROPIC_API_KEY": "sk-..."}
    cli_flags = Column(
        JSONB, nullable=False, default=dict
    )  # {"--model": "opus", "--max-turns": "10"}
    command_templates = Column(
        JSONB, nullable=False, default=dict
    )  # {"generate": "cat {prompt_file} | claude --print", "task": "...", "check": "..."}
    enabled = Column(Boolean, nullable=False, default=True)
    # Install metadata (moved from hardcoded SUPPORTED_AGENTS dict)
    agent_type = Column(Text, nullable=False, default="cli_binary")  # "cli_binary" or "api_service"
    install_cmd = Column(Text, nullable=True)  # shell command to install binary
    post_install_cmd = Column(
        Text, nullable=True
    )  # shell command for plugins/tools (runs after auth)
    check_cmd = Column(Text, nullable=True)  # command to verify installed
    prereq_check = Column(Text, nullable=True)  # command to verify prerequisites
    prereq_name = Column(Text, nullable=True)  # human-readable prereq description
    needs_non_root = Column(
        Boolean, nullable=False, default=False
    )  # whether agent refuses root execution
    consolidated_default = Column(
        Boolean, nullable=False, default=True
    )  # whether agent prefers consolidated mode (plan+code+review in one invocation)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

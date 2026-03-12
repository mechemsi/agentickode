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


class TaskRun(Base):
    __tablename__ = "task_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_type = Column(Text, nullable=False, default="ai_task")
    task_id = Column(Text, nullable=False)
    project_id = Column(Text, ForeignKey("project_configs.project_id"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    branch_name = Column(Text, nullable=False)
    workspace_path = Column(Text, nullable=False)
    repo_owner = Column(Text, nullable=False, default="")
    repo_name = Column(Text, nullable=False, default="")
    default_branch = Column(Text, nullable=False, default="main")
    task_source = Column(Text, nullable=False, default="plane")
    git_provider = Column(Text, nullable=False, default="gitea")
    task_source_meta = Column(JSONB, nullable=False, default=dict)
    use_claude_api = Column(Boolean, nullable=False, default=False)
    workspace_config = Column(JSONB, nullable=True)

    # State machine
    status = Column(Text, nullable=False, default="pending")
    current_phase = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)

    # Phase results
    workspace_result = Column(JSONB, nullable=True)
    planning_result = Column(JSONB, nullable=True)
    coding_results = Column(JSONB, nullable=True)
    test_results = Column(JSONB, nullable=True)
    review_result = Column(JSONB, nullable=True)

    # Approval
    pr_url = Column(Text, nullable=True)
    approved = Column(Boolean, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    approval_requested_at = Column(DateTime(timezone=True), nullable=True)

    # Timing
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    phase_started_at = Column(DateTime(timezone=True), nullable=True)

    # Workflow linkage
    parent_run_id = Column(Integer, ForeignKey("task_runs.id"), nullable=True)
    workflow_template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=True)

    project = relationship("ProjectConfig", back_populates="runs")
    logs = relationship("TaskLog", back_populates="run", cascade="all, delete-orphan")
    phase_executions = relationship(
        "PhaseExecution",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="PhaseExecution.order_index",
    )
    webhook_callbacks = relationship(
        "WebhookCallback", back_populates="run", cascade="all, delete-orphan"
    )
    agent_invocations = relationship(
        "AgentInvocation", back_populates="run", cascade="all, delete-orphan"
    )
    parent_run = relationship("TaskRun", remote_side="TaskRun.id", foreign_keys=[parent_run_id])
    child_runs = relationship("TaskRun", foreign_keys=[parent_run_id], overlaps="parent_run")


class PhaseExecution(Base):
    __tablename__ = "phase_executions"
    __table_args__ = (UniqueConstraint("run_id", "phase_name", name="uq_run_phase"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False)
    phase_name = Column(Text, nullable=False)
    order_index = Column(Integer, nullable=False)
    trigger_mode = Column(Text, nullable=False, default="auto")
    status = Column(Text, nullable=False, default="pending")
    result = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    agent_override = Column(Text, nullable=True)
    notify_source = Column(Boolean, nullable=False, default=False)
    phase_config = Column(JSONB, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    run = relationship("TaskRun", back_populates="phase_executions")


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    level = Column(Text, nullable=False, default="info")
    phase = Column(Text, nullable=True)
    message = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)

    run = relationship("TaskRun", back_populates="logs")


class AgentInvocation(Base):
    __tablename__ = "agent_invocations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False)
    phase_execution_id = Column(
        Integer, ForeignKey("phase_executions.id", ondelete="SET NULL"), nullable=True
    )
    workspace_server_id = Column(
        Integer, ForeignKey("workspace_servers.id", ondelete="SET NULL"), nullable=True
    )
    agent_name = Column(Text, nullable=False)  # "claude", "codex", "ollama/qwen2.5", etc.
    phase_name = Column(Text, nullable=True)  # "coding", "reviewing", "planning"
    subtask_index = Column(Integer, nullable=True)  # for coding: which subtask (0-based)
    subtask_title = Column(Text, nullable=True)

    # Full content storage
    prompt_text = Column(Text, nullable=True)  # full prompt sent to agent
    response_text = Column(Text, nullable=True)  # full agent response
    system_prompt_text = Column(Text, nullable=True)  # system prompt used

    # Metrics
    prompt_chars = Column(Integer, nullable=False, default=0)
    response_chars = Column(Integer, nullable=False, default=0)
    exit_code = Column(Integer, nullable=True)
    files_changed = Column(JSONB, nullable=True)  # list of filenames
    duration_seconds = Column(Float, nullable=True)

    # Cost tracking
    estimated_tokens_in = Column(Integer, nullable=True)
    estimated_tokens_out = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)

    # Status
    status = Column(
        Text, nullable=False, default="running"
    )  # "running", "success", "failed", "timeout"
    error_message = Column(Text, nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Session continuity
    session_id = Column(Text, nullable=True, index=True)

    # Extra
    metadata_ = Column("metadata_", JSONB, nullable=True)  # command used, etc.

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run = relationship("TaskRun", back_populates="agent_invocations")
    phase_execution = relationship("PhaseExecution")
    workspace_server = relationship("WorkspaceServer")
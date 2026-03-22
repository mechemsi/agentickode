# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add autonomous agent loop support: autonomy_config, agent_plan, follow_up_tasks, and new tables.

Revision ID: 023
Revises: 022
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "023"
down_revision = "022"


def upgrade() -> None:
    # project_configs: autonomy configuration
    op.add_column(
        "project_configs",
        sa.Column("autonomy_config", JSONB(), nullable=True, server_default="{}"),
    )

    # task_runs: agent loop result fields
    op.add_column(
        "task_runs",
        sa.Column("agent_plan", JSONB(), nullable=True),
    )
    op.add_column(
        "task_runs",
        sa.Column("follow_up_tasks", JSONB(), nullable=True),
    )

    # scheduled_tasks: cron-triggered recurring tasks
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("schedule", sa.Text(), nullable=False),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # monitoring_rules: alert-triggered tasks
    op.create_table(
        "monitoring_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("min_severity", sa.Text(), nullable=False, server_default="error"),
        sa.Column("task_template", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # agent_loop_executions: tracks autonomous agent loop runs
    op.create_table(
        "agent_loop_executions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_run_id", sa.Integer(), sa.ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("progress_snapshots", JSONB(), nullable=False, server_default="[]"),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # notification_sources: Slack/Discord bot config per project
    op.create_table(
        "notification_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("notification_sources")
    op.drop_table("agent_loop_executions")
    op.drop_table("monitoring_rules")
    op.drop_table("scheduled_tasks")
    op.drop_column("task_runs", "follow_up_tasks")
    op.drop_column("task_runs", "agent_plan")
    op.drop_column("project_configs", "autonomy_config")

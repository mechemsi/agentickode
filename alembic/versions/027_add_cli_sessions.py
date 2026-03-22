# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add cli_sessions table for persistent CLI agent sessions.

Revision ID: 027
Revises: 026
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "027"
down_revision = "026"


def upgrade() -> None:
    op.create_table(
        "cli_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "workspace_server_id",
            sa.Integer(),
            sa.ForeignKey("workspace_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("project_configs.project_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "task_run_id",
            sa.Integer(),
            sa.ForeignKey("task_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("user_context", sa.Text(), nullable=False, server_default="coder"),
        sa.Column("workspace_path", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("tmux_session", sa.Text(), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="starting"),
        sa.Column("remote_control_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("remote_control_port", sa.Integer(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("cli_sessions")

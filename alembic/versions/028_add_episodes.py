# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add episodes table and episodic tracking columns to agent_loop_executions.

Revision ID: 028
Revises: 027
"""

import sqlalchemy as sa

from alembic import op

revision = "028"
down_revision = "027"


def upgrade() -> None:
    # Episodes table for bounded autonomous execution episodes
    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "agent_loop_execution_id",
            sa.Integer(),
            sa.ForeignKey("agent_loop_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("git_checkpoint_sha", sa.Text(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("context_usage_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("stall_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # Episodic tracking columns on agent_loop_executions
    op.add_column(
        "agent_loop_executions",
        sa.Column("recovery_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_loop_executions",
        sa.Column("last_checkpoint_sha", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_loop_executions",
        sa.Column("total_episodes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_loop_executions",
        sa.Column("total_turns", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_loop_executions",
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("agent_loop_executions", "total_tokens")
    op.drop_column("agent_loop_executions", "total_turns")
    op.drop_column("agent_loop_executions", "total_episodes")
    op.drop_column("agent_loop_executions", "last_checkpoint_sha")
    op.drop_column("agent_loop_executions", "recovery_count")
    op.drop_table("episodes")

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add local_terminal_sessions table for persistent local agent terminals.

Revision ID: 033
Revises: 032
"""

import sqlalchemy as sa

from alembic import op

revision = "033"
down_revision = "032"


def upgrade() -> None:
    op.create_table(
        "local_terminal_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Text(), unique=True, nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("tmux_name", sa.Text(), unique=True, nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("local_terminal_sessions")

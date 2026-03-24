# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add agent_policies table for per-project safety and budget controls.

Revision ID: 029
Revises: 028
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "029"
down_revision = "028"


def upgrade() -> None:
    op.create_table(
        "agent_policies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("project_configs.project_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("max_budget_usd", sa.Float(), nullable=True),
        sa.Column("max_turns_per_episode", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("max_episodes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "max_total_duration_seconds", sa.Integer(), nullable=False, server_default="7200"
        ),
        sa.Column("stall_timeout_seconds", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("max_files_changed", sa.Integer(), nullable=True),
        sa.Column("allowed_file_patterns", JSONB, nullable=False, server_default="[]"),
        sa.Column("denied_file_patterns", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_policies")

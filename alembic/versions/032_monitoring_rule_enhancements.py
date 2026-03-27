# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add dedup and last_triggered columns to monitoring_rules.

Revision ID: 032
Revises: 031
"""

import sqlalchemy as sa

from alembic import op

revision = "032"
down_revision = "031"


def upgrade() -> None:
    op.add_column(
        "monitoring_rules",
        sa.Column("dedup_window_seconds", sa.Integer(), nullable=True, server_default="3600"),
    )
    op.add_column(
        "monitoring_rules",
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monitoring_rules", "last_triggered_at")
    op.drop_column("monitoring_rules", "dedup_window_seconds")

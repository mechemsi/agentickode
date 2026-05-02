# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add polling fields and generic integration_config to project_configs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_configs",
        sa.Column("poll_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "project_configs",
        sa.Column(
            "poll_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )
    op.add_column(
        "project_configs",
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_configs",
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_configs",
        sa.Column(
            "integration_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("project_configs", "integration_config")
    op.drop_column("project_configs", "next_poll_at")
    op.drop_column("project_configs", "last_polled_at")
    op.drop_column("project_configs", "poll_interval_minutes")
    op.drop_column("project_configs", "poll_enabled")

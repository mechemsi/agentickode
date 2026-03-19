# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add agent_creates_pr to agent_settings.

Revision ID: 022
Revises: 021
"""

import sqlalchemy as sa

from alembic import op

revision = "022"
down_revision = "021"


def upgrade() -> None:
    op.add_column(
        "agent_settings",
        sa.Column("agent_creates_pr", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("agent_settings", "agent_creates_pr")

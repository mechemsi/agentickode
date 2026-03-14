# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add consolidated_default to agent_settings.

Revision ID: 020
Revises: 019
"""

import sqlalchemy as sa

from alembic import op

revision = "020"
down_revision = "019"


def upgrade() -> None:
    op.add_column(
        "agent_settings",
        sa.Column("consolidated_default", sa.Boolean(), nullable=False, server_default="true"),
    )
    # API-based agents need external orchestration — set to False
    op.execute(
        "UPDATE agent_settings SET consolidated_default = false " "WHERE agent_type = 'api_service'"
    )


def downgrade() -> None:
    op.drop_column("agent_settings", "consolidated_default")

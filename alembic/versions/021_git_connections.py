# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Create git_connections table.

Revision ID: 021
Revises: 020
"""

import sqlalchemy as sa

from alembic import op

revision = "021"
down_revision = "020"


def upgrade() -> None:
    op.create_table(
        "git_connections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("token_enc", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False, server_default="global"),
        sa.Column(
            "workspace_server_id",
            sa.Integer(),
            sa.ForeignKey("workspace_servers.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("project_configs.project_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("git_connections")

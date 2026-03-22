# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add server_groups table and server_group_id FK on workspace_servers.

Revision ID: 026
Revises: 025
"""

import sqlalchemy as sa

from alembic import op

revision = "026"
down_revision = "025"


def upgrade() -> None:
    op.create_table(
        "server_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("git_token_encrypted", sa.Text(), nullable=True),
        sa.Column("git_provider_type", sa.Text(), nullable=True),
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
    op.add_column(
        "workspace_servers",
        sa.Column(
            "server_group_id",
            sa.Integer(),
            sa.ForeignKey("server_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "workspace_servers",
        sa.Column(
            "max_concurrent_tasks",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("workspace_servers", "max_concurrent_tasks")
    op.drop_column("workspace_servers", "server_group_id")
    op.drop_table("server_groups")

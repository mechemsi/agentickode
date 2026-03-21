# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add project_workspace_servers join table for M:N project-to-workspace relationship.

Revision ID: 024
Revises: 023
"""

import sqlalchemy as sa

from alembic import op

revision = "024"
down_revision = "023"


def upgrade() -> None:
    # 1. Create the project_workspace_servers join table
    op.create_table(
        "project_workspace_servers",
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("project_configs.project_id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "workspace_server_id",
            sa.Integer(),
            sa.ForeignKey("workspace_servers.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "idx_project_workspace_servers_project",
        "project_workspace_servers",
        ["project_id"],
    )
    op.create_index(
        "idx_project_workspace_servers_server",
        "project_workspace_servers",
        ["workspace_server_id"],
    )

    # 2. Migrate existing data from project_configs.workspace_server_id into the join table
    op.execute(
        """
        INSERT INTO project_workspace_servers (project_id, workspace_server_id, priority)
        SELECT project_id, workspace_server_id, 0
        FROM project_configs
        WHERE workspace_server_id IS NOT NULL
        """
    )

    # 3. Add workspace_server_id FK column to task_runs (nullable)
    op.add_column(
        "task_runs",
        sa.Column(
            "workspace_server_id",
            sa.Integer(),
            sa.ForeignKey("workspace_servers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 4. Backfill task_runs.workspace_server_id from the project's old single workspace server
    op.execute(
        """
        UPDATE task_runs tr
        SET workspace_server_id = pc.workspace_server_id
        FROM project_configs pc
        WHERE tr.project_id = pc.project_id
          AND pc.workspace_server_id IS NOT NULL
        """
    )

    # 5. Drop workspace_server_id from project_configs
    op.drop_column("project_configs", "workspace_server_id")


def downgrade() -> None:
    # Re-add workspace_server_id to project_configs
    op.add_column(
        "project_configs",
        sa.Column(
            "workspace_server_id",
            sa.Integer(),
            sa.ForeignKey("workspace_servers.id"),
            nullable=True,
        ),
    )

    # Restore from join table (take the lowest-priority entry per project)
    op.execute(
        """
        UPDATE project_configs pc
        SET workspace_server_id = pws.workspace_server_id
        FROM (
            SELECT DISTINCT ON (project_id) project_id, workspace_server_id
            FROM project_workspace_servers
            ORDER BY project_id, priority ASC
        ) pws
        WHERE pc.project_id = pws.project_id
        """
    )

    # Drop task_runs.workspace_server_id
    op.drop_column("task_runs", "workspace_server_id")

    # Drop indexes and join table
    op.drop_index("idx_project_workspace_servers_server", table_name="project_workspace_servers")
    op.drop_index("idx_project_workspace_servers_project", table_name="project_workspace_servers")
    op.drop_table("project_workspace_servers")

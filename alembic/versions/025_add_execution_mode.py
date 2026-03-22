# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add execution_mode column to task_runs.

Revision ID: 025
Revises: 024
"""

import sqlalchemy as sa

from alembic import op

revision = "025"
down_revision = "024"


def upgrade() -> None:
    op.add_column(
        "task_runs",
        sa.Column("execution_mode", sa.Text(), nullable=False, server_default="structured"),
    )


def downgrade() -> None:
    op.drop_column("task_runs", "execution_mode")

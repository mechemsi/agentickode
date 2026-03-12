"""Add worker_user columns to workspace_servers

Revision ID: 009
Revises: 008
Create Date: 2026-02-20
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workspace_servers", sa.Column("worker_user", sa.Text(), nullable=True))
    op.add_column("workspace_servers", sa.Column("worker_user_status", sa.Text(), nullable=True))
    op.add_column("workspace_servers", sa.Column("worker_user_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspace_servers", "worker_user_error")
    op.drop_column("workspace_servers", "worker_user_status")
    op.drop_column("workspace_servers", "worker_user")

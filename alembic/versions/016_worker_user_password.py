"""Add worker_user_password to workspace_servers

Revision ID: 016
Revises: 015
Create Date: 2026-03-01
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workspace_servers", sa.Column("worker_user_password", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspace_servers", "worker_user_password")

"""Add workspace_path to project_configs

Revision ID: 008
Revises: 007
Create Date: 2026-02-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project_configs", sa.Column("workspace_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_configs", "workspace_path")

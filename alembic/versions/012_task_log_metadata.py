"""Add metadata JSONB column to task_logs table.

Revision ID: 012
Revises: 011
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "012"
down_revision = "011"


def upgrade() -> None:
    op.add_column("task_logs", sa.Column("metadata", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("task_logs", "metadata")

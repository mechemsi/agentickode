"""Add git_provider_token_enc to project_configs.

Revision ID: 019
Revises: 018
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"


def upgrade() -> None:
    op.add_column("project_configs", sa.Column("git_provider_token_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_configs", "git_provider_token_enc")

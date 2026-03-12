"""Add post_install_cmd to agent_settings.

Revision ID: 018
Revises: 017
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"


def upgrade() -> None:
    op.add_column("agent_settings", sa.Column("post_install_cmd", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_settings", "post_install_cmd")

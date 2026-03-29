# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add last_command to local_terminal_sessions for resume support."""

from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "local_terminal_sessions",
        sa.Column("last_command", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("local_terminal_sessions", "last_command")

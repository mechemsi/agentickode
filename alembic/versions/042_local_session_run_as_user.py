# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Local terminal sessions: store run-as user.

Adds ``local_terminal_sessions.run_as_user`` (nullable) so a tmux session can be
recreated/attached as the same OS user it was launched under. Null = root
(pre-existing behaviour).
"""

from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE local_terminal_sessions ADD COLUMN IF NOT EXISTS run_as_user TEXT"
    )


def downgrade() -> None:
    op.drop_column("local_terminal_sessions", "run_as_user")

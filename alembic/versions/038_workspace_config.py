# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add workspace-config columns to project_config.

- ``local_path``: optional absolute path to an already-checked-out git repo on
  the workspace server. When set, ``workspace_setup`` skips the clone/fetch
  step and operates on this folder in place (worktrees still isolate runs).
- ``worker_user_override``: per-project override for the OS user agents run
  as. Takes precedence over ``WorkspaceServer.worker_user``. A step's
  ``params.run_as`` overrides this in turn.

Both columns are nullable; existing rows keep today's behavior (clone every
run, use server default user).
"""

import sqlalchemy as sa

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_configs",
        sa.Column("local_path", sa.Text(), nullable=True),
    )
    op.add_column(
        "project_configs",
        sa.Column("worker_user_override", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_configs", "worker_user_override")
    op.drop_column("project_configs", "local_path")

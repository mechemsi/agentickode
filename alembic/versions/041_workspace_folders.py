# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Multiple workspace folders per server.

Adds ``workspace_servers.workspace_folders`` (JSONB list[str]) — extra scan
roots beyond the primary ``workspace_root``. Additive and nullable, so existing
servers are unaffected (null = no extra folders).
"""

from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent ADD: the runtime auto-migrate (main.py) may have already added
    # this column without advancing alembic_version, so a plain op.add_column
    # would raise DuplicateColumnError on ``alembic upgrade head``.
    op.execute(
        "ALTER TABLE workspace_servers ADD COLUMN IF NOT EXISTS workspace_folders JSONB"
    )


def downgrade() -> None:
    op.drop_column("workspace_servers", "workspace_folders")

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add host-bridge fields to workspace_servers.

When the platform server (server_type='local') has these two fields
set, the backend routes commands through ``scripts/host_bridge.py``
running on the operator's host instead of executing them in-container.

- ``bridge_url``: e.g. ``http://host.docker.internal:17777``
- ``bridge_token_enc``: encrypted bearer token (see services/encryption)

Both nullable; existing rows keep ``LocalCommandService`` behavior.
"""

import sqlalchemy as sa

from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_servers",
        sa.Column("bridge_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "workspace_servers",
        sa.Column("bridge_token_enc", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_servers", "bridge_token_enc")
    op.drop_column("workspace_servers", "bridge_url")

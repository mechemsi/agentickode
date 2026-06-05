# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Drop the role tables — the roles abstraction was removed.

Workflow steps now name agents directly (see migration 039). The role →
RoleAssignment → agent indirection and its prompt config tables are gone:

- ``role_prompt_overrides`` (per-role/agent prompt overrides)
- ``role_configs`` (per-role prompts + temperature/num_predict)
- ``role_assignments`` (role → agent/ollama mapping cascade)

Dropped in FK order. Irreversible — the data is not recoverable, so
``downgrade`` raises rather than silently recreating empty tables.
"""

from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS role_prompt_overrides CASCADE")
    op.execute("DROP TABLE IF EXISTS role_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS role_assignments CASCADE")


def downgrade() -> None:
    raise NotImplementedError("Role tables were removed permanently; downgrade is not supported.")

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Direct-agent selection: replace the roles abstraction.

Additive columns that let a workflow step run an agent directly instead of via
a role → RoleAssignment cascade:

- ``agent_settings.is_default``: the one global default agent (seeded: claude)
  used when a step doesn't name an agent and the project has no override.
- ``agent_settings.minimal_mode``: skip the system prompt for this agent (the
  behavior previously held in ``role_prompt_overrides.minimal_mode`` for claude).
- ``project_configs.default_agent``: per-project default agent; overrides the
  global ``is_default`` when set.

All nullable / defaulted — existing rows keep working.
"""

from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent ADDs: the runtime auto-migrate (main.py ``_run_migrations``) may have
    # already added these columns without advancing ``alembic_version``, so a plain
    # ``op.add_column`` would raise DuplicateColumnError on ``alembic upgrade head``.
    op.execute(
        "ALTER TABLE agent_settings "
        "ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE agent_settings "
        "ADD COLUMN IF NOT EXISTS minimal_mode BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute("ALTER TABLE project_configs ADD COLUMN IF NOT EXISTS default_agent TEXT")
    # Seed the global default agent.
    op.execute("UPDATE agent_settings SET is_default = true WHERE agent_name = 'claude'")
    op.execute("UPDATE agent_settings SET minimal_mode = true WHERE agent_name = 'claude'")


def downgrade() -> None:
    op.drop_column("project_configs", "default_agent")
    op.drop_column("agent_settings", "minimal_mode")
    op.drop_column("agent_settings", "is_default")

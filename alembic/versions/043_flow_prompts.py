# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Flow prompts (ADR-009) — additive, Phase 1.

Adds the ``flow_prompts`` table and a nullable ``task_runs.flow_prompt_id`` FK.
Purely additive: nothing is removed, and the flow-prompt execution path is gated
behind the ``FLOW_PROMPTS_ENABLED`` setting (off by default). Workflow templates
continue to work unchanged.
"""

from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS flow_prompts (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            flow_type TEXT NOT NULL DEFAULT 'implement',
            prompt TEXT NOT NULL,
            agent TEXT,
            agent_mode TEXT NOT NULL DEFAULT 'task',
            extra_data_sources JSONB,
            triggers JSONB,
            is_system BOOLEAN NOT NULL DEFAULT FALSE,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS flow_prompt_id INTEGER "
        "REFERENCES flow_prompts(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.drop_column("task_runs", "flow_prompt_id")
    op.execute("DROP TABLE IF EXISTS flow_prompts")

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Drop the legacy workflow-template / phase-execution engine (ADR-009, Phase 5).

IRREVERSIBLE. Removes the multi-step dispatch engine now that every run is a
single flow-prompt agent call:

* ``task_runs.workflow_template_id`` FK column
* ``agent_invocations.phase_execution_id`` FK column
* ``phase_executions`` table (historical per-step records — lost, accepted)
* ``workflow_templates`` table (custom + seeded templates — lost, accepted)

FK-bearing columns are dropped before their referenced tables. ``downgrade`` only
recreates empty table shells / nullable columns — the data is gone and cannot be
restored, so the real rollback path is fix-forward, not ``down``.
"""

from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop FK columns first so the referenced tables can be dropped cleanly.
    op.execute("ALTER TABLE task_runs DROP COLUMN IF EXISTS workflow_template_id")
    op.execute("ALTER TABLE agent_invocations DROP COLUMN IF EXISTS phase_execution_id")
    op.execute("DROP TABLE IF EXISTS phase_executions")
    op.execute("DROP TABLE IF EXISTS workflow_templates")


def downgrade() -> None:
    # IRREVERSIBLE: recreates empty shells only — no data is restored.
    op.execute("""
        CREATE TABLE IF NOT EXISTS workflow_templates (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            label_rules JSONB NOT NULL DEFAULT '[]',
            triggers JSONB NOT NULL DEFAULT '[]',
            phases JSONB NOT NULL DEFAULT '[]',
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            is_system BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS phase_executions (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
            phase_name TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            trigger_mode TEXT NOT NULL DEFAULT 'auto',
            status TEXT NOT NULL DEFAULT 'pending',
            result JSONB,
            error_message TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            agent_override TEXT,
            notify_source BOOLEAN NOT NULL DEFAULT FALSE,
            phase_config JSONB,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_run_phase UNIQUE (run_id, phase_name)
        )
    """)
    op.execute(
        "ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS workflow_template_id INTEGER "
        "REFERENCES workflow_templates(id)"
    )
    op.execute(
        "ALTER TABLE agent_invocations ADD COLUMN IF NOT EXISTS phase_execution_id INTEGER "
        "REFERENCES phase_executions(id) ON DELETE SET NULL"
    )

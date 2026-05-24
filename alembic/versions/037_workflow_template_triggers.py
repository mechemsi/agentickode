# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add `triggers` JSONB column to workflow_templates and backfill from label_rules.

Triggers are the new first-class way to route external events (webhooks, schedules,
manual API hits) to a WorkflowTemplate. Existing `label_rules` rows are copied into
`triggers` as ``LabelTrigger(source='any')`` entries so behavior is preserved.

`label_rules` is kept (NOT dropped) for one release as a fallback path used by
``WorkflowTemplateRepository.match_labels``.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_templates",
        sa.Column(
            "triggers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # Backfill: copy any existing label_rules into triggers as LabelTrigger entries.
    # Uses Postgres JSONB functions; safe to skip on dialects without jsonb_agg
    # (SQLite test DBs run create_all without migrations, so this is Postgres-only
    # at runtime).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE workflow_templates
            SET triggers = COALESCE((
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'type', 'label',
                        'source', 'any',
                        'match_all', COALESCE(r->'match_all', '[]'::jsonb),
                        'match_any', COALESCE(r->'match_any', '[]'::jsonb)
                    )
                )
                FROM jsonb_array_elements(label_rules) r
            ), '[]'::jsonb)
            WHERE jsonb_array_length(label_rules) > 0
            """
        )


def downgrade() -> None:
    op.drop_column("workflow_templates", "triggers")

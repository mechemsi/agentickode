"""Seed 6 predefined workflow templates.

Revision ID: 011
Revises: 010
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"

# Phase helper: build a phase config dict
_P = lambda name, enabled=True, trigger="auto": {  # noqa: E731
    "phase_name": name,
    "enabled": enabled,
    "role": None,
    "agent_override": None,
    "trigger_mode": trigger,
    "notify_source": False,
    "timeout_seconds": None,
    "params": {},
}

TEMPLATES = [
    {
        "name": "default",
        "description": "Full end-to-end AI task workflow",
        "is_default": True,
        "is_system": True,
        "label_rules": json.dumps([]),
        "phases": json.dumps([
            _P("workspace_setup"),
            _P("init"),
            _P("planning"),
            _P("coding"),
            _P("testing"),
            _P("reviewing"),
            _P("approval", trigger="wait_for_approval"),
            _P("finalization"),
        ]),
    },
    {
        "name": "planner",
        "description": "Analyze task and decompose into subtasks",
        "is_default": False,
        "is_system": True,
        "label_rules": json.dumps([{"match_all": [], "match_any": ["plan-only", "decompose"]}]),
        "phases": json.dumps([
            _P("workspace_setup"),
            _P("init"),
            _P("planning"),
            _P("task_creation"),
            _P("finalization"),
        ]),
    },
    {
        "name": "hotfix",
        "description": "Quick coding without planning phase",
        "is_default": False,
        "is_system": True,
        "label_rules": json.dumps([{"match_all": [], "match_any": ["hotfix", "quick-fix"]}]),
        "phases": json.dumps([
            _P("workspace_setup"),
            _P("init"),
            _P("coding"),
            _P("testing"),
            _P("reviewing"),
            _P("approval", trigger="wait_for_approval"),
            _P("finalization"),
        ]),
    },
    {
        "name": "small-task",
        "description": "Execute a pre-planned subtask (child of planner)",
        "is_default": False,
        "is_system": True,
        "label_rules": json.dumps([{"match_all": [], "match_any": ["subtask"]}]),
        "phases": json.dumps([
            _P("workspace_setup"),
            _P("init"),
            _P("coding"),
            _P("testing"),
            _P("reviewing"),
            _P("approval", trigger="wait_for_approval"),
            _P("finalization"),
        ]),
    },
    {
        "name": "pr-review",
        "description": "Review an existing PR/MR via API",
        "is_default": False,
        "is_system": True,
        "label_rules": json.dumps([{"match_all": [], "match_any": ["review-pr", "pr-review"]}]),
        "phases": json.dumps([
            _P("pr_fetch"),
            _P("reviewing"),
            _P("finalization"),
        ]),
    },
    {
        "name": "fix-pr",
        "description": "Fix code after PR review feedback",
        "is_default": False,
        "is_system": True,
        "label_rules": json.dumps([{"match_all": [], "match_any": ["fix-pr", "pr-fix"]}]),
        "phases": json.dumps([
            _P("pr_fetch"),
            _P("workspace_setup"),
            _P("init"),
            _P("coding"),
            _P("reviewing"),
            _P("finalization"),
        ]),
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    # Remove any existing templates with same names to avoid conflicts
    for t in TEMPLATES:
        conn.execute(
            sa.text("DELETE FROM workflow_templates WHERE name = :name"),
            {"name": t["name"]},
        )

    # Insert using raw SQL with CAST for PostgreSQL JSONB compatibility
    for t in TEMPLATES:
        conn.execute(
            sa.text(
                "INSERT INTO workflow_templates "
                "(name, description, label_rules, phases, is_default, is_system) "
                "VALUES (:name, :description, CAST(:label_rules AS jsonb), "
                "CAST(:phases AS jsonb), :is_default, :is_system)"
            ),
            {
                "name": t["name"],
                "description": t["description"],
                "label_rules": t["label_rules"],
                "phases": t["phases"],
                "is_default": t["is_default"],
                "is_system": t["is_system"],
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM workflow_templates WHERE is_system = :val"),
        {"val": True},
    )

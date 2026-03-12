"""Add agent_configs and workflow_templates tables

Revision ID: 005
Revises: 004
Create Date: 2026-02-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_name", sa.Text(), unique=True, nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("user_prompt_template", sa.Text(), nullable=False, server_default=""),
        sa.Column("phase_binding", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("default_temperature", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("default_num_predict", sa.Integer(), nullable=False, server_default="2048"),
        sa.Column("extra_params", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("label_rules", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("phases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Triggers for updated_at
    op.execute("""
        CREATE TRIGGER trg_agent_configs_updated
        BEFORE UPDATE ON agent_configs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    """)
    op.execute("""
        CREATE TRIGGER trg_workflow_templates_updated
        BEFORE UPDATE ON workflow_templates
        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    """)

    # Seed default agents
    op.execute("""
        INSERT INTO agent_configs (agent_name, display_name, description, system_prompt, user_prompt_template, phase_binding, is_system, default_temperature, default_num_predict)
        VALUES
        (
            'planner', 'Planner', 'Senior software architect for task decomposition',
            'You are a senior software architect specializing in task decomposition.

You analyze tasks and break them down into specific, implementable subtasks ordered by dependency.',
            '## Task
Title: {title}
Description: {description}

## Project Context
{context_text}

## Instructions
1. Analyze the task requirements
2. Break down into specific, implementable subtasks
3. Order subtasks by dependency (what must be done first)
4. Estimate complexity (simple/medium/complex)

Respond in JSON format:
{{
  "subtasks": [
    {{"id": 1, "title": "...", "description": "...", "files_likely_affected": ["..."]}}
  ],
  "estimated_complexity": "simple|medium|complex",
  "notes": "Any important considerations"
}}',
            'planning', true, 0.3, 2048
        ),
        (
            'coder', 'Coder', 'Expert software developer for implementing code changes',
            'You are an expert software developer implementing code changes.

Follow existing code patterns and style. Add appropriate error handling. Write or update tests if applicable. Commit changes with descriptive messages.',
            '## Subtask
{title}

## Description
{description}

## Files Likely Affected
{files}

## Previous Changes in This Session
{prev}

## Instructions
1. Implement the subtask as described
2. Follow existing code patterns and style
3. Add appropriate error handling
4. Write or update tests if applicable
5. Commit changes with a descriptive message',
            'coding', true, 0.3, 2048
        ),
        (
            'reviewer', 'Reviewer', 'Senior code reviewer for ensuring code quality',
            'You are a senior code reviewer. Review changes for correctness, quality, error handling, security, and performance.',
            '## Task Context
Title: {title}
Description: {description}

## Files Changed
{files_changed}

## Diff
```diff
{diff_text}
```

## Review Criteria
1. Code correctness - does it implement the requirement?
2. Code quality - is it readable, maintainable?
3. Error handling - are edge cases covered?
4. Security - any vulnerabilities introduced?
5. Performance - any obvious inefficiencies?

Respond in JSON format:
{{
  "approved": true,
  "issues": [
    {{"severity": "critical|major|minor", "file": "...", "line": 0, "description": "..."}}
  ],
  "suggestions": ["..."]
}}',
            'reviewing', true, 0.2, 2048
        ),
        (
            'fast', 'Fast', 'Fast, concise coding assistant',
            'You are a fast, concise coding assistant.',
            '',
            NULL, false, 0.3, 2048
        );
    """)

    # Seed default workflow template
    op.execute("""
        INSERT INTO workflow_templates (name, description, label_rules, phases, is_default)
        VALUES (
            'default',
            'Standard 7-phase pipeline',
            '[]',
            '[
                {"phase_name": "workspace_setup", "enabled": true, "agent_override": null, "timeout_seconds": null, "params": {}},
                {"phase_name": "init", "enabled": true, "agent_override": null, "timeout_seconds": null, "params": {}},
                {"phase_name": "planning", "enabled": true, "agent_override": null, "timeout_seconds": null, "params": {}},
                {"phase_name": "coding", "enabled": true, "agent_override": null, "timeout_seconds": null, "params": {}},
                {"phase_name": "reviewing", "enabled": true, "agent_override": null, "timeout_seconds": null, "params": {}},
                {"phase_name": "approval", "enabled": true, "agent_override": null, "timeout_seconds": null, "params": {}},
                {"phase_name": "finalization", "enabled": true, "agent_override": null, "timeout_seconds": null, "params": {}}
            ]',
            true
        );
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_workflow_templates_updated ON workflow_templates")
    op.execute("DROP TRIGGER IF EXISTS trg_agent_configs_updated ON agent_configs")
    op.drop_table("workflow_templates")
    op.drop_table("agent_configs")

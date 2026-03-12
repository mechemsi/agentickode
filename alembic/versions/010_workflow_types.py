"""Add workflow type columns: is_system, parent_run_id, workflow_template_id.

Revision ID: 010
Revises: 009
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"


def upgrade() -> None:
    op.add_column(
        "workflow_templates",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "task_runs",
        sa.Column("parent_run_id", sa.Integer(), sa.ForeignKey("task_runs.id"), nullable=True),
    )
    op.add_column(
        "task_runs",
        sa.Column(
            "workflow_template_id",
            sa.Integer(),
            sa.ForeignKey("workflow_templates.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("task_runs", "workflow_template_id")
    op.drop_column("task_runs", "parent_run_id")
    op.drop_column("workflow_templates", "is_system")

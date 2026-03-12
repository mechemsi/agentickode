"""Create agent_invocations table with cost tracking fields.

Revision ID: 013
Revises: 012
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "013"
down_revision = "012"


def upgrade() -> None:
    op.create_table(
        "agent_invocations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("task_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "phase_execution_id",
            sa.Integer,
            sa.ForeignKey("phase_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_server_id",
            sa.Integer,
            sa.ForeignKey("workspace_servers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_name", sa.Text, nullable=False),
        sa.Column("phase_name", sa.Text, nullable=True),
        sa.Column("subtask_index", sa.Integer, nullable=True),
        sa.Column("subtask_title", sa.Text, nullable=True),
        # Full content storage
        sa.Column("prompt_text", sa.Text, nullable=True),
        sa.Column("response_text", sa.Text, nullable=True),
        sa.Column("system_prompt_text", sa.Text, nullable=True),
        # Metrics
        sa.Column("prompt_chars", sa.Integer, nullable=False, server_default="0"),
        sa.Column("response_chars", sa.Integer, nullable=False, server_default="0"),
        sa.Column("exit_code", sa.Integer, nullable=True),
        sa.Column("files_changed", JSONB, nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        # Cost tracking
        sa.Column("estimated_tokens_in", sa.Integer, nullable=True),
        sa.Column("estimated_tokens_out", sa.Integer, nullable=True),
        sa.Column("estimated_cost_usd", sa.Float, nullable=True),
        # Status
        sa.Column("status", sa.Text, nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text, nullable=True),
        # Timing
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Session continuity
        sa.Column("session_id", sa.Text, nullable=True, index=True),
        # Extra
        sa.Column("metadata_", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_invocations")

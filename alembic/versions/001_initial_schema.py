"""Initial schema: project_configs, task_runs, task_logs

Revision ID: 001
Revises:
Create Date: 2026-02-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # project_configs (matches existing init-metadata-db.sql)
    op.create_table(
        "project_configs",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("project_slug", sa.Text(), nullable=False),
        sa.Column("repo_owner", sa.Text(), nullable=False),
        sa.Column("repo_name", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.Text(), nullable=False, server_default="main"),
        sa.Column("task_source", sa.Text(), nullable=False, server_default="plane"),
        sa.Column("git_provider", sa.Text(), nullable=False, server_default="gitea"),
        sa.Column("workspace_config", postgresql.JSONB(), nullable=True),
        sa.Column("ai_config", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_project_configs_slug", "project_configs", ["project_slug"])
    op.create_index("idx_project_configs_repo", "project_configs", ["git_provider", "repo_owner", "repo_name"])

    # task_runs
    op.create_table(
        "task_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_type", sa.Text(), nullable=False, server_default="ai_task"),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("project_configs.project_id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("branch_name", sa.Text(), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column("repo_owner", sa.Text(), nullable=False, server_default=""),
        sa.Column("repo_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("default_branch", sa.Text(), nullable=False, server_default="main"),
        sa.Column("task_source", sa.Text(), nullable=False, server_default="plane"),
        sa.Column("git_provider", sa.Text(), nullable=False, server_default="gitea"),
        sa.Column("task_source_meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("use_claude_api", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("workspace_config", postgresql.JSONB(), nullable=True),
        # State machine
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("current_phase", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_message", sa.Text(), nullable=True),
        # Phase results
        sa.Column("workspace_result", postgresql.JSONB(), nullable=True),
        sa.Column("planning_result", postgresql.JSONB(), nullable=True),
        sa.Column("coding_results", postgresql.JSONB(), nullable=True),
        sa.Column("test_results", postgresql.JSONB(), nullable=True),
        sa.Column("review_result", postgresql.JSONB(), nullable=True),
        # Approval
        sa.Column("pr_url", sa.Text(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True),
        # Timing
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_task_runs_status", "task_runs", ["status"])
    op.create_index("idx_task_runs_project", "task_runs", ["project_id"])

    # task_logs
    op.create_table(
        "task_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("level", sa.Text(), nullable=False, server_default="info"),
        sa.Column("phase", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index("idx_task_logs_run", "task_logs", ["run_id"])

    # updated_at trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("project_configs", "task_runs"):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
        """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_task_runs_updated ON task_runs")
    op.execute("DROP TRIGGER IF EXISTS trg_project_configs_updated ON project_configs")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at()")
    op.drop_table("task_logs")
    op.drop_table("task_runs")
    op.drop_table("project_configs")

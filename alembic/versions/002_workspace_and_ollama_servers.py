"""Add workspace_servers, discovered_agents, ollama_servers, llm_role_assignments

Revision ID: 002
Revises: 001
Create Date: 2026-02-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # workspace_servers
    op.create_table(
        "workspace_servers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("hostname", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("username", sa.Text(), nullable=False, server_default="root"),
        sa.Column("ssh_key_path", sa.Text(), nullable=True),
        sa.Column("workspace_root", sa.Text(), nullable=False, server_default="/workspaces"),
        sa.Column("status", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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

    # discovered_agents
    op.create_table(
        "discovered_agents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_server_id",
            sa.Integer(),
            sa.ForeignKey("workspace_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("agent_type", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("workspace_server_id", "agent_name", name="uq_server_agent"),
    )
    op.create_index(
        "idx_discovered_agents_server", "discovered_agents", ["workspace_server_id"]
    )

    # ollama_servers
    op.create_table(
        "ollama_servers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cached_models", postgresql.JSONB(), nullable=True),
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

    # llm_role_assignments
    op.create_table(
        "llm_role_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("role", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "ollama_server_id",
            sa.Integer(),
            sa.ForeignKey("ollama_servers.id"),
            nullable=False,
        ),
        sa.Column("model_name", sa.Text(), nullable=False),
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
    op.create_index(
        "idx_llm_role_assignments_server", "llm_role_assignments", ["ollama_server_id"]
    )

    # Add workspace_server_id FK to project_configs
    op.add_column(
        "project_configs",
        sa.Column(
            "workspace_server_id",
            sa.Integer(),
            sa.ForeignKey("workspace_servers.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_project_configs_workspace_server",
        "project_configs",
        ["workspace_server_id"],
    )

    # updated_at triggers for new tables
    for table in ("workspace_servers", "ollama_servers", "llm_role_assignments"):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
        """)


def downgrade() -> None:
    for table in ("llm_role_assignments", "ollama_servers", "workspace_servers"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated ON {table}")

    op.drop_index("idx_project_configs_workspace_server", "project_configs")
    op.drop_column("project_configs", "workspace_server_id")
    op.drop_table("llm_role_assignments")
    op.drop_table("ollama_servers")
    op.drop_index("idx_discovered_agents_server", "discovered_agents")
    op.drop_table("discovered_agents")
    op.drop_table("workspace_servers")

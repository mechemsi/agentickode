"""Replace llm_role_assignments with unified role_assignments table

Revision ID: 003
Revises: 002
Create Date: 2026-02-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create new role_assignments table
    op.create_table(
        "role_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=False),
        sa.Column(
            "ollama_server_id",
            sa.Integer(),
            sa.ForeignKey("ollama_servers.id"),
            nullable=True,
        ),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column(
            "workspace_server_id",
            sa.Integer(),
            sa.ForeignKey("workspace_servers.id"),
            nullable=True,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint(
            "role", "workspace_server_id", "priority", name="uq_role_scope_priority"
        ),
    )
    op.create_index(
        "idx_role_assignments_server", "role_assignments", ["ollama_server_id"]
    )
    op.create_index(
        "idx_role_assignments_workspace", "role_assignments", ["workspace_server_id"]
    )

    # 2. Migrate existing data from llm_role_assignments
    op.execute("""
        INSERT INTO role_assignments (role, provider_type, ollama_server_id, model_name, priority, created_at, updated_at)
        SELECT role, 'ollama', ollama_server_id, model_name, 0, created_at, updated_at
        FROM llm_role_assignments
    """)

    # 3. Drop old table and its trigger
    op.execute(
        "DROP TRIGGER IF EXISTS trg_llm_role_assignments_updated ON llm_role_assignments"
    )
    op.drop_index("idx_llm_role_assignments_server", "llm_role_assignments")
    op.drop_table("llm_role_assignments")

    # 4. Add updated_at trigger for new table
    op.execute("""
        CREATE TRIGGER trg_role_assignments_updated
        BEFORE UPDATE ON role_assignments
        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    """)


def downgrade() -> None:
    # Recreate old table
    op.execute("DROP TRIGGER IF EXISTS trg_role_assignments_updated ON role_assignments")

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

    # Migrate back (only ollama rows with priority=0 and no workspace scope)
    op.execute("""
        INSERT INTO llm_role_assignments (role, ollama_server_id, model_name, created_at, updated_at)
        SELECT role, ollama_server_id, model_name, created_at, updated_at
        FROM role_assignments
        WHERE provider_type = 'ollama' AND workspace_server_id IS NULL AND priority = 0
    """)

    op.drop_index("idx_role_assignments_workspace", "role_assignments")
    op.drop_index("idx_role_assignments_server", "role_assignments")
    op.drop_table("role_assignments")

    op.execute("""
        CREATE TRIGGER trg_llm_role_assignments_updated
        BEFORE UPDATE ON llm_role_assignments
        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
    """)

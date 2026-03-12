"""Add project instructions, secrets, and instruction versions tables

Revision ID: 017
Revises: 016
Create Date: 2026-03-06
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_instructions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_name", sa.Text(), nullable=False, server_default="__global__"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "phase_name", name="uq_project_phase"),
    )

    op.create_table(
        "project_secrets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Text(), sa.ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("inject_as", sa.Text(), nullable=False, server_default="env_var"),
        sa.Column("phase_scope", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "name", name="uq_project_secret_name"),
    )

    op.create_table(
        "project_instruction_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instruction_id", sa.Integer(), sa.ForeignKey("project_instructions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("change_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("project_instruction_versions")
    op.drop_table("project_secrets")
    op.drop_table("project_instructions")

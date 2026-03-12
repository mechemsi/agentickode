"""Create agent_settings, agent_prompt_overrides, and app_settings tables.

Revision ID: 014
Revises: 013
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "014"
down_revision = "013"


def upgrade() -> None:
    op.create_table(
        "agent_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_name", sa.Text, unique=True, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("supports_session", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("default_timeout", sa.Integer, nullable=False, server_default="600"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="1"),
        sa.Column("environment_vars", JSONB, nullable=False, server_default="{}"),
        sa.Column("cli_flags", JSONB, nullable=False, server_default="{}"),
        sa.Column("command_templates", JSONB, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        # Install metadata
        sa.Column("agent_type", sa.Text, nullable=False, server_default="cli_binary"),
        sa.Column("install_cmd", sa.Text, nullable=True),
        sa.Column("check_cmd", sa.Text, nullable=True),
        sa.Column("prereq_check", sa.Text, nullable=True),
        sa.Column("prereq_name", sa.Text, nullable=True),
        sa.Column("needs_non_root", sa.Boolean, nullable=False, server_default="false"),
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
        "agent_prompt_overrides",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "agent_config_id",
            sa.Integer,
            sa.ForeignKey("agent_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cli_agent_name", sa.Text, nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("user_prompt_template", sa.Text, nullable=True),
        sa.Column("minimal_mode", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("extra_params", JSONB, nullable=False, server_default="{}"),
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
        sa.UniqueConstraint("agent_config_id", "cli_agent_name", name="uq_config_agent"),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", JSONB, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("agent_prompt_overrides")
    op.drop_table("agent_settings")

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Add ON DELETE CASCADE to FKs that blocked server and project deletes.

Without these clauses, deleting a workspace_server with any role_assignments
raises a ForeignKeyViolationError, and deleting a project_config triggers an
ORM nullification of task_runs.project_id which violates its NOT NULL
constraint.
"""

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "role_assignments_workspace_server_id_fkey",
        "role_assignments",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "role_assignments_workspace_server_id_fkey",
        "role_assignments",
        "workspace_servers",
        ["workspace_server_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "role_assignments_ollama_server_id_fkey",
        "role_assignments",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "role_assignments_ollama_server_id_fkey",
        "role_assignments",
        "ollama_servers",
        ["ollama_server_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "task_runs_project_id_fkey",
        "task_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "task_runs_project_id_fkey",
        "task_runs",
        "project_configs",
        ["project_id"],
        ["project_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "task_runs_project_id_fkey",
        "task_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "task_runs_project_id_fkey",
        "task_runs",
        "project_configs",
        ["project_id"],
        ["project_id"],
    )

    op.drop_constraint(
        "role_assignments_ollama_server_id_fkey",
        "role_assignments",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "role_assignments_ollama_server_id_fkey",
        "role_assignments",
        "ollama_servers",
        ["ollama_server_id"],
        ["id"],
    )

    op.drop_constraint(
        "role_assignments_workspace_server_id_fkey",
        "role_assignments",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "role_assignments_workspace_server_id_fkey",
        "role_assignments",
        "workspace_servers",
        ["workspace_server_id"],
        ["id"],
    )

# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Registry of exportable entities with their metadata."""

from __future__ import annotations

from dataclasses import dataclass

from backend.models import (
    AgentSettings,
    AppSetting,
    FlowPrompt,
    NotificationChannel,
    OllamaServer,
    ProjectConfig,
    WorkspaceServer,
)


@dataclass(frozen=True)
class FKMapping:
    """Describes how to resolve an integer FK to a human-readable name."""

    column: str  # FK column on this model, e.g. "workspace_server_id"
    target_model: type  # referenced model class
    target_name_col: str  # column on target used as export key
    export_field: str  # name used in the JSON envelope


@dataclass(frozen=True)
class ChildConfig:
    """Describes a nested child collection."""

    relationship_attr: str  # attribute on parent ORM object
    model: type
    excluded_fields: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SecretField:
    """Describes a field that may contain secrets."""

    column: str
    is_dict: bool = False  # True → encrypt/redact dict values


@dataclass(frozen=True)
class EntityConfig:
    model: type
    export_key: str  # key in the entities dict, e.g. "workspace_servers"
    match_fields: tuple[str, ...]  # used to detect conflicts on import
    excluded_fields: frozenset[str] = frozenset()
    fk_mappings: tuple[FKMapping, ...] = ()
    secret_fields: tuple[SecretField, ...] = ()
    children: tuple[ChildConfig, ...] = ()


_COMMON_EXCLUDED: frozenset[str] = frozenset({"created_at", "updated_at"})


ENTITY_CONFIGS: dict[str, EntityConfig] = {
    "workspace_servers": EntityConfig(
        model=WorkspaceServer,
        export_key="workspace_servers",
        match_fields=("name",),
        excluded_fields=_COMMON_EXCLUDED
        | {
            "id",
            "last_seen_at",
            "status",
            "error_message",
            "worker_user_status",
            "worker_user_error",
            "setup_log",
        },
        secret_fields=(SecretField("worker_user_password"),),
    ),
    "ollama_servers": EntityConfig(
        model=OllamaServer,
        export_key="ollama_servers",
        match_fields=("name",),
        excluded_fields=_COMMON_EXCLUDED
        | {
            "id",
            "last_seen_at",
            "status",
            "error_message",
            "cached_models",
        },
    ),
    "app_settings": EntityConfig(
        model=AppSetting,
        export_key="app_settings",
        match_fields=("key",),
        excluded_fields=frozenset({"updated_at"}),
    ),
    "agent_settings": EntityConfig(
        model=AgentSettings,
        export_key="agent_settings",
        match_fields=("agent_name",),
        excluded_fields=_COMMON_EXCLUDED | {"id"},
        secret_fields=(SecretField("environment_vars", is_dict=True),),
    ),
    "notification_channels": EntityConfig(
        model=NotificationChannel,
        export_key="notification_channels",
        match_fields=("name", "channel_type"),
        excluded_fields=_COMMON_EXCLUDED | {"id"},
        secret_fields=(SecretField("config", is_dict=True),),
    ),
    "flow_prompts": EntityConfig(
        model=FlowPrompt,
        export_key="flow_prompts",
        match_fields=("name",),
        excluded_fields=_COMMON_EXCLUDED | {"id"},
    ),
    "project_configs": EntityConfig(
        model=ProjectConfig,
        export_key="project_configs",
        match_fields=("project_id",),
        excluded_fields=_COMMON_EXCLUDED,
        # TODO(Task4): add workspace_servers export via project_workspace_servers join table
    ),
}

# Import must follow this order to satisfy FK constraints.
DEPENDENCY_ORDER: list[str] = [
    # Tier 1 — no FK deps
    "workspace_servers",
    "ollama_servers",
    "app_settings",
    "agent_settings",
    "notification_channels",
    "flow_prompts",
    # Tier 2 — depends on T1
    "project_configs",
]

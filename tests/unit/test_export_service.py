# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for ExportService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    AgentSettings,
    AppSetting,
    NotificationChannel,
    OllamaServer,
    ProjectConfig,
    RoleAssignment,
    RoleConfig,
    RolePromptOverride,
    WorkflowTemplate,
    WorkspaceServer,
)
from backend.services.backup.export_service import ExportService
from backend.services.backup.schema_version import CURRENT_SCHEMA_VERSION
from backend.services.backup.secret_handler import REDACTED, SecretMode


async def _seed(session: AsyncSession) -> None:
    ws = WorkspaceServer(
        name="ws-01",
        hostname="10.0.0.1",
        port=22,
        username="root",
        workspace_root="/workspaces",
        worker_user_password="secret-pw",
    )
    session.add(ws)
    await session.flush()

    ollama = OllamaServer(name="ollama-01", url="http://ollama:11434")
    session.add(ollama)
    await session.flush()

    session.add(AppSetting(key="theme", value={"mode": "dark"}))
    session.add(
        AgentSettings(
            agent_name="claude",
            display_name="Claude CLI",
            environment_vars={"ANTHROPIC_API_KEY": "sk-secret"},
        )
    )
    session.add(
        NotificationChannel(
            name="alerts",
            channel_type="telegram",
            config={"bot_token": "tok-secret", "chat_id": "123"},
            events=["run.completed"],
        )
    )
    session.add(WorkflowTemplate(name="default", description="Default workflow"))
    session.add(
        ProjectConfig(
            project_id="proj-1",
            project_slug="proj-1",
            repo_owner="org",
            repo_name="repo",
            workspace_server_id=ws.id,
        )
    )
    rc = RoleConfig(
        agent_name="planner",
        display_name="Planner",
        system_prompt="You are a planner.",
    )
    session.add(rc)
    await session.flush()
    session.add(
        RolePromptOverride(
            role_config_id=rc.id,
            cli_agent_name="claude",
            system_prompt="Plan with Claude",
        )
    )
    session.add(
        RoleAssignment(
            role="coder",
            provider_type="agent",
            agent_name="claude",
            workspace_server_id=ws.id,
            ollama_server_id=ollama.id,
            priority=0,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_export_full_redacted(db_session: AsyncSession):
    await _seed(db_session)
    svc = ExportService(db_session)
    envelope = await svc.export_config(secret_mode=SecretMode.redacted)

    inner = envelope["autodev_export"]
    assert inner["schema_version"] == CURRENT_SCHEMA_VERSION
    assert inner["secret_mode"] == "redacted"
    assert "encryption_salt" not in inner

    entities = inner["entities"]
    assert len(entities["workspace_servers"]) == 1
    ws = entities["workspace_servers"][0]
    assert ws["name"] == "ws-01"
    assert ws["worker_user_password"] == REDACTED
    assert "id" not in ws
    assert "status" not in ws

    assert len(entities["project_configs"]) == 1
    proj = entities["project_configs"][0]
    assert proj["workspace_server_name"] == "ws-01"
    assert "workspace_server_id" not in proj

    assert len(entities["agent_settings"]) == 1
    ag = entities["agent_settings"][0]
    assert ag["environment_vars"]["ANTHROPIC_API_KEY"] == REDACTED

    assert len(entities["notification_channels"]) == 1
    nc = entities["notification_channels"][0]
    assert nc["config"]["bot_token"] == REDACTED

    assert len(entities["role_configs"]) == 1
    rc = entities["role_configs"][0]
    assert len(rc["prompt_overrides"]) == 1

    assert len(entities["role_assignments"]) == 1
    ra = entities["role_assignments"][0]
    assert ra["workspace_server_name"] == "ws-01"
    assert ra["ollama_server_name"] == "ollama-01"


@pytest.mark.asyncio
async def test_export_encrypted(db_session: AsyncSession):
    await _seed(db_session)
    svc = ExportService(db_session)
    envelope = await svc.export_config(secret_mode=SecretMode.encrypted, password="test")
    inner = envelope["autodev_export"]
    assert inner["secret_mode"] == "encrypted"
    assert "encryption_salt" in inner

    ws = inner["entities"]["workspace_servers"][0]
    assert ws["worker_user_password"] != "secret-pw"
    assert ws["worker_user_password"] != REDACTED


@pytest.mark.asyncio
async def test_export_selected_types(db_session: AsyncSession):
    await _seed(db_session)
    svc = ExportService(db_session)
    envelope = await svc.export_config(entity_types=["app_settings", "workspace_servers"])
    entities = envelope["autodev_export"]["entities"]
    assert "app_settings" in entities
    assert "workspace_servers" in entities
    assert "project_configs" not in entities


@pytest.mark.asyncio
async def test_export_single_project(db_session: AsyncSession):
    await _seed(db_session)
    svc = ExportService(db_session)
    envelope = await svc.export_project("proj-1")
    entities = envelope["autodev_export"]["entities"]
    assert len(entities["project_configs"]) == 1
    assert "workspace_servers" in entities


@pytest.mark.asyncio
async def test_export_project_not_found(db_session: AsyncSession):
    svc = ExportService(db_session)
    with pytest.raises(ValueError, match="not found"):
        await svc.export_project("nonexistent")
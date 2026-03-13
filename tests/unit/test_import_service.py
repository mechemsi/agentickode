# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Tests for ImportService — preview, execute, roundtrip."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    AppSetting,
    OllamaServer,
    ProjectConfig,
    RoleConfig,
    WorkspaceServer,
)
from backend.services.backup.export_service import ExportService
from backend.services.backup.import_service import ImportService
from backend.services.backup.secret_handler import SecretMode


async def _seed_source(session: AsyncSession) -> None:
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

    session.add(OllamaServer(name="ollama-01", url="http://ollama:11434"))
    session.add(AppSetting(key="theme", value={"mode": "dark"}))
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
    await session.commit()


@pytest.mark.asyncio
async def test_preview(db_session: AsyncSession):
    await _seed_source(db_session)
    export_svc = ExportService(db_session)
    envelope = await export_svc.export_config(secret_mode=SecretMode.plaintext)

    # Previewing on the same DB should show "update" for all entities
    import_svc = ImportService(db_session)
    result = await import_svc.preview(envelope)
    entities = result["entities"]
    for key, items in entities.items():
        for item in items:
            assert item["action"] == "update", f"{key}: expected update"


@pytest.mark.asyncio
async def test_import_skip(db_session: AsyncSession):
    await _seed_source(db_session)
    export_svc = ExportService(db_session)
    envelope = await export_svc.export_config(secret_mode=SecretMode.plaintext)

    # Import with skip → everything skipped
    import_svc = ImportService(db_session)
    result = await import_svc.execute(envelope, conflict_resolution="skip")
    for key, stats in result["entities"].items():
        assert stats["created"] == 0, f"{key}: should not create"
        assert stats["updated"] == 0, f"{key}: should not update"


@pytest.mark.asyncio
async def test_import_overwrite(db_session: AsyncSession):
    await _seed_source(db_session)
    export_svc = ExportService(db_session)
    envelope = await export_svc.export_config(secret_mode=SecretMode.plaintext)

    # Modify an existing value
    ws_data = envelope["agentickode_export"]["entities"]["workspace_servers"][0]
    ws_data["hostname"] = "10.0.0.99"

    import_svc = ImportService(db_session)
    result = await import_svc.execute(envelope, conflict_resolution="overwrite")
    ws_stats = result["entities"]["workspace_servers"]
    assert ws_stats["updated"] == 1

    # Verify the hostname was updated
    row = (
        await db_session.execute(select(WorkspaceServer).where(WorkspaceServer.name == "ws-01"))
    ).scalar_one()
    assert row.hostname == "10.0.0.99"


@pytest.mark.asyncio
async def test_roundtrip_encrypted(db_session: AsyncSession):
    """Export encrypted → import on clean DB → verify data."""
    await _seed_source(db_session)
    export_svc = ExportService(db_session)
    envelope = await export_svc.export_config(
        secret_mode=SecretMode.encrypted, password="roundtrip"
    )

    # Delete existing data to simulate import into a clean DB
    await db_session.execute(select(ProjectConfig).where(True))  # force load
    for model in [ProjectConfig, RoleConfig, AppSetting, OllamaServer, WorkspaceServer]:
        rows = (await db_session.execute(select(model))).scalars().all()
        for row in rows:
            await db_session.delete(row)
    await db_session.commit()

    # Import
    import_svc = ImportService(db_session)
    await import_svc.execute(envelope, conflict_resolution="skip", password="roundtrip")

    # Verify workspace server restored with decrypted secret
    ws = (
        await db_session.execute(select(WorkspaceServer).where(WorkspaceServer.name == "ws-01"))
    ).scalar_one()
    assert ws.hostname == "10.0.0.1"
    assert ws.worker_user_password == "secret-pw"


@pytest.mark.asyncio
async def test_import_invalid_version(db_session: AsyncSession):
    bad_data = {
        "agentickode_export": {
            "schema_version": "99.0.0",
            "secret_mode": "plaintext",
            "entities": {},
        }
    }
    import_svc = ImportService(db_session)
    with pytest.raises(ValueError, match="Unsupported schema version"):
        await import_svc.preview(bad_data)

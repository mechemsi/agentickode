# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Shared fixtures for all tests.

Uses an in-memory SQLite database (via aiosqlite) so tests run without
any external PostgreSQL dependency. JSONB columns are mapped to SQLite JSON.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.types import JSON

from backend.models import Base
from backend.services.chromadb_service import ChromaDBService
from backend.services.container import ServiceContainer
from backend.services.ollama_service import OllamaService
from backend.services.openhands_service import OpenHandsService


@event.listens_for(Base.metadata, "column_reflect")
def _map_jsonb(inspector, table, column_info):
    if isinstance(column_info["type"], JSONB):
        column_info["type"] = JSON()


def _render_jsonb_as_json(metadata):
    """Replace JSONB columns with JSON for SQLite compatibility."""
    for table in metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest.fixture()
async def db_engine():
    """Create an async in-memory SQLite engine with all tables."""
    _render_jsonb_as_json(Base.metadata)
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean async session per test."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture()
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with the FastAPI app, using in-memory DB.

    Patches `get_db` to use the test database and disables the worker.
    """
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    # Patch worker so it doesn't start during tests
    with patch("backend.main.WorkerEngine") as mock_worker_cls:
        mock_worker_cls.return_value = AsyncMock()
        mock_worker_cls.return_value.run = AsyncMock()
        mock_worker_cls.return_value.stop = AsyncMock()

        from backend.database import get_db
        from backend.main import app

        app.dependency_overrides[get_db] = _override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.clear()


@pytest.fixture()
def mock_services() -> ServiceContainer:
    """ServiceContainer with all services mocked."""
    from backend.services.role_resolver import RoleResolver

    ollama = AsyncMock(spec=OllamaService)
    openhands = AsyncMock(spec=OpenHandsService)
    chromadb = AsyncMock(spec=ChromaDBService)
    role_resolver = AsyncMock(spec=RoleResolver)
    return ServiceContainer(
        ollama=ollama,
        openhands=openhands,
        chromadb=chromadb,
        role_resolver=role_resolver,
    )


@pytest.fixture()
def make_task_run():
    """Factory for creating TaskRun instances with sensible defaults."""
    from backend.models import TaskRun

    def _make(**overrides):
        defaults = {
            "task_id": "TASK-1",
            "project_id": "proj-1",
            "title": "Test task",
            "description": "A test description",
            "branch_name": "feature/ai-TASK-1",
            "workspace_path": "/workspaces/proj-1",
            "repo_owner": "org",
            "repo_name": "repo",
            "default_branch": "main",
            "task_source": "plane",
            "git_provider": "gitea",
            "task_source_meta": {},
            "status": "pending",
            "max_retries": 3,
        }
        defaults.update(overrides)
        return TaskRun(**defaults)

    return _make

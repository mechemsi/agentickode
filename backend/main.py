# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api import (
    agents,
    analytics,
    app_settings,
    backup,
    git_connections,
    health,
    llm_roles,
    logs,
    notification_channels,
    ollama_servers,
    project_instructions,
    project_issues,
    projects,
    role_configs,
    runs,
    runs_actions,
    runs_phases,
    sse,
    webhook_callbacks,
    webhooks,
    webhooks_pr,
    workflow_templates,
    ws,
)
from backend.api.servers import (
    agent_management_router,
    git_access_router,
    server_projects_router,
    ssh_keys_router,
    worker_user_router,
    workspace_servers_router,
    ws_discovery_router,
    ws_ops_router,
)
from backend.database import engine as db_engine
from backend.seed import seed_all
from backend.services.http_client import close_http_client
from backend.services.notifications.dispatcher import NotificationDispatcher
from backend.worker.engine import WorkerEngine

logger = logging.getLogger("agentickode")

worker_engine = WorkerEngine()
notification_dispatcher = NotificationDispatcher()


async def _run_migration_step(sql: str) -> None:
    """Run a single migration step in its own transaction."""
    try:
        async with db_engine.begin() as conn:
            await conn.execute(text(sql))
    except Exception:
        pass  # Column/table already exists — safe to ignore


async def _run_migrations() -> None:
    """Run lightweight auto-migrations for new columns/tables."""
    await _run_migration_step("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await _run_migration_step("ALTER TABLE workspace_servers ADD COLUMN setup_log JSONB")
    await _run_migration_step("""
        CREATE TABLE IF NOT EXISTS agent_settings (
            id SERIAL PRIMARY KEY,
            agent_name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            supports_session BOOLEAN NOT NULL DEFAULT FALSE,
            default_timeout INTEGER NOT NULL DEFAULT 600,
            max_retries INTEGER NOT NULL DEFAULT 1,
            environment_vars JSONB NOT NULL DEFAULT '{}',
            cli_flags JSONB NOT NULL DEFAULT '{}',
            command_templates JSONB NOT NULL DEFAULT '{}',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # Rename agent_configs → role_configs (existing installations)
    await _run_migration_step("ALTER TABLE agent_configs RENAME TO role_configs")
    await _run_migration_step("ALTER TABLE agent_prompt_overrides RENAME TO role_prompt_overrides")
    await _run_migration_step(
        "ALTER TABLE role_prompt_overrides RENAME COLUMN agent_config_id TO role_config_id"
    )
    await _run_migration_step("""
        CREATE TABLE IF NOT EXISTS role_prompt_overrides (
            id SERIAL PRIMARY KEY,
            role_config_id INTEGER NOT NULL REFERENCES role_configs(id) ON DELETE CASCADE,
            cli_agent_name TEXT NOT NULL,
            system_prompt TEXT,
            user_prompt_template TEXT,
            minimal_mode BOOLEAN NOT NULL DEFAULT FALSE,
            extra_params JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(role_config_id, cli_agent_name)
        )
    """)
    # Add user_context to discovered_agents (admin vs worker)
    await _run_migration_step(
        "ALTER TABLE discovered_agents ADD COLUMN user_context VARCHAR(20) NOT NULL DEFAULT 'admin'"
    )
    await _run_migration_step("DROP INDEX IF EXISTS uq_server_agent")
    await _run_migration_step(
        "ALTER TABLE discovered_agents DROP CONSTRAINT IF EXISTS uq_server_agent"
    )
    await _run_migration_step("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_server_agent_ctx
        ON discovered_agents (workspace_server_id, agent_name, user_context)
    """)
    # Backfill: duplicate existing admin agents as worker agents
    await _run_migration_step("""
        INSERT INTO discovered_agents
            (workspace_server_id, agent_name, user_context, agent_type, path, version, available, metadata, discovered_at)
        SELECT workspace_server_id, agent_name, 'worker', agent_type, path, version, available, metadata, discovered_at
        FROM discovered_agents
        WHERE user_context = 'admin'
        ON CONFLICT (workspace_server_id, agent_name, user_context) DO NOTHING
    """)
    await _run_migration_step("""
        CREATE TABLE IF NOT EXISTS agent_invocations (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES task_runs(id) ON DELETE CASCADE,
            phase_execution_id INTEGER REFERENCES phase_executions(id) ON DELETE SET NULL,
            workspace_server_id INTEGER REFERENCES workspace_servers(id) ON DELETE SET NULL,
            agent_name TEXT NOT NULL,
            phase_name TEXT,
            subtask_index INTEGER,
            subtask_title TEXT,
            prompt_text TEXT,
            response_text TEXT,
            system_prompt_text TEXT,
            prompt_chars INTEGER NOT NULL DEFAULT 0,
            response_chars INTEGER NOT NULL DEFAULT 0,
            exit_code INTEGER,
            files_changed JSONB,
            duration_seconds FLOAT,
            status TEXT NOT NULL DEFAULT 'running',
            error_message TEXT,
            session_id TEXT,
            metadata_ JSONB NOT NULL DEFAULT '{}',
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )
    logger.info("Starting agentickode backend")
    await _run_migrations()
    from backend.database import async_session

    async with async_session() as db:
        await seed_all(db)
    worker_task = asyncio.create_task(worker_engine.run())
    notification_dispatcher.start()
    yield
    logger.info("Shutting down worker")
    notification_dispatcher.stop()
    worker_engine.stop()
    worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker_task
    await close_http_client()


app = FastAPI(title="AgenticKode", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(webhooks.router, prefix="/api")
app.include_router(webhooks_pr.router, prefix="/api")
app.include_router(sse.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(runs_actions.router, prefix="/api")
app.include_router(runs_phases.router, prefix="/api")
app.include_router(project_instructions.router, prefix="/api")
app.include_router(project_issues.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(workspace_servers_router, prefix="/api")
app.include_router(ws_discovery_router, prefix="/api")
app.include_router(ws_ops_router, prefix="/api")
app.include_router(git_access_router, prefix="/api")
app.include_router(agent_management_router, prefix="/api")
app.include_router(server_projects_router, prefix="/api")
app.include_router(ollama_servers.router, prefix="/api")
app.include_router(llm_roles.router, prefix="/api")
app.include_router(ssh_keys_router, prefix="/api")
app.include_router(notification_channels.router, prefix="/api")
app.include_router(role_configs.router, prefix="/api")
app.include_router(workflow_templates.router, prefix="/api")
app.include_router(webhook_callbacks.router, prefix="/api")
app.include_router(worker_user_router, prefix="/api")
app.include_router(app_settings.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
app.include_router(git_connections.router, prefix="/api")
app.include_router(ws.router)

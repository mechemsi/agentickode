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
    agent_control,
    agent_query,
    agent_setup,
    agent_stream,
    agents,
    analytics,
    app_settings,
    automation_rules,
    backup,
    chat,
    git_connections,
    health,
    llm_roles,
    local_terminals,
    logs,
    memory,
    monitoring_rules,
    notification_channels,
    ollama_servers,
    platform_crons,
    project_instructions,
    project_issues,
    projects,
    role_configs,
    runs,
    runs_actions,
    runs_phases,
    scheduled_tasks,
    sse,
    webhook_callbacks,
    webhooks,
    webhooks_discord,
    webhooks_linear,
    webhooks_monitoring,
    webhooks_pr,
    webhooks_pr_comment,
    webhooks_slack,
    workflow_templates,
    workspace_commands,
    ws,
    ws_office,
)
from backend.api.servers import (
    agent_management_router,
    docker_management_router,
    git_access_router,
    readiness_router,
    server_groups_router,
    server_projects_router,
    sessions_router,
    ssh_keys_router,
    worker_user_router,
    workspace_servers_router,
    ws_discovery_router,
    ws_ops_router,
)
from backend.database import engine as db_engine
from backend.mcp.server import get_mcp_app
from backend.seed import seed_all
from backend.services.http_client import close_http_client
from backend.services.notifications.dispatcher import NotificationDispatcher
from backend.services.queue_service import queue_service
from backend.services.rules_dispatcher import RulesDispatcher
from backend.services.task_management.status_sync import StatusSyncer
from backend.worker.engine import WorkerEngine
from backend.worker.issue_poller_scheduler import IssuePollerScheduler
from backend.worker.platform_cron_scheduler import PlatformCronScheduler
from backend.worker.schedule_trigger_scheduler import ScheduleTriggerScheduler
from backend.worker.scheduler import TaskScheduler
from backend.worker.worktree_cleanup_scheduler import WorktreeCleanupScheduler

logger = logging.getLogger("agentickode")

worker_engine = WorkerEngine()
notification_dispatcher = NotificationDispatcher()
rules_dispatcher = RulesDispatcher()
status_syncer = StatusSyncer()


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
            default_timeout INTEGER NOT NULL DEFAULT 3600,
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
    await _run_migration_step(
        "ALTER TABLE workspace_servers ADD COLUMN max_concurrent_tasks INTEGER NOT NULL DEFAULT 1"
    )
    # Server groups table and FK
    await _run_migration_step("""
        CREATE TABLE IF NOT EXISTS server_groups (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            git_token_encrypted TEXT,
            git_provider_type TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await _run_migration_step(
        "ALTER TABLE workspace_servers ADD COLUMN server_group_id INTEGER "
        "REFERENCES server_groups(id) ON DELETE SET NULL"
    )
    # workspace_readiness table for dev-toolchain validation per (project, server)
    await _run_migration_step("""
        CREATE TABLE IF NOT EXISTS workspace_readiness (
            id SERIAL PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES project_configs(project_id) ON DELETE CASCADE,
            workspace_server_id INTEGER NOT NULL REFERENCES workspace_servers(id) ON DELETE CASCADE,
            validation_status TEXT NOT NULL DEFAULT 'pending',
            validated_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            check_results JSONB,
            validation_report JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(project_id, workspace_server_id)
        )
    """)
    # cli_sessions table for persistent CLI agent sessions
    await _run_migration_step("""
        CREATE TABLE IF NOT EXISTS cli_sessions (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL UNIQUE,
            workspace_server_id INT NOT NULL REFERENCES workspace_servers(id) ON DELETE CASCADE,
            project_id TEXT REFERENCES project_configs(project_id) ON DELETE SET NULL,
            task_run_id INT REFERENCES task_runs(id) ON DELETE SET NULL,
            agent_name TEXT NOT NULL,
            user_context TEXT NOT NULL DEFAULT 'coder',
            workspace_path TEXT,
            display_name TEXT,
            tmux_session TEXT NOT NULL,
            pid INT,
            status TEXT NOT NULL DEFAULT 'starting',
            remote_control_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            remote_control_port INT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at TIMESTAMPTZ,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await _run_migration_step("ALTER TABLE local_terminal_sessions ADD COLUMN last_command TEXT")
    await _run_migration_step(
        "ALTER TABLE local_terminal_sessions ADD COLUMN agent_session_id TEXT"
    )
    # Platform-as-server: server_type column (local vs remote)
    await _run_migration_step(
        "ALTER TABLE workspace_servers " "ADD COLUMN server_type TEXT NOT NULL DEFAULT 'remote'"
    )
    # Polling fields + generic integration_config on project_configs
    await _run_migration_step(
        "ALTER TABLE project_configs ADD COLUMN poll_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    )
    await _run_migration_step(
        "ALTER TABLE project_configs ADD COLUMN poll_interval_minutes INTEGER NOT NULL DEFAULT 5"
    )
    await _run_migration_step("ALTER TABLE project_configs ADD COLUMN last_polled_at TIMESTAMPTZ")
    await _run_migration_step("ALTER TABLE project_configs ADD COLUMN next_poll_at TIMESTAMPTZ")
    await _run_migration_step(
        "ALTER TABLE project_configs "
        "ADD COLUMN integration_config JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    await _run_migration_step("""
        CREATE TABLE IF NOT EXISTS platform_crons (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            schedule TEXT NOT NULL,
            prompt TEXT NOT NULL,
            session_id TEXT,
            agent_name TEXT NOT NULL DEFAULT 'claude',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            next_run_at TIMESTAMPTZ,
            last_run_at TIMESTAMPTZ,
            last_result TEXT,
            run_count INTEGER NOT NULL DEFAULT 0,
            execution_log JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ
        )
    """)


async def _cleanup_orphaned_sessions() -> None:
    """Delete local terminal sessions whose tmux is gone (container restart)."""
    from backend.database import async_session

    async with async_session() as db:
        result = await db.execute(
            text("SELECT id, tmux_name FROM local_terminal_sessions WHERE status = 'active'")
        )
        rows = result.fetchall()
        if not rows:
            return

        for row in rows:
            proc = await asyncio.create_subprocess_shell(
                f"tmux has-session -t {row.tmux_name} 2>/dev/null",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()
            if proc.returncode != 0:
                await db.execute(
                    text("DELETE FROM local_terminal_sessions WHERE id = :id"),
                    {"id": row.id},
                )
        await db.commit()
        logger.info("Cleaned up orphaned local terminal sessions")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )
    logger.info("Starting agentickode backend")
    await _run_migrations()
    await queue_service.connect()
    from backend.database import async_session

    async with async_session() as db:
        await seed_all(db)

    # Mark orphaned local terminal sessions as closed (tmux died on restart)
    await _cleanup_orphaned_sessions()

    worker_task = asyncio.create_task(worker_engine.run())
    notification_dispatcher.start()
    rules_dispatcher.start()
    status_syncer.start()
    scheduler = TaskScheduler(async_session)
    scheduler_task = asyncio.create_task(scheduler.run())
    cron_scheduler = PlatformCronScheduler(async_session)
    cron_scheduler_task = asyncio.create_task(cron_scheduler.run())
    issue_poller = IssuePollerScheduler(async_session)
    issue_poller_task = asyncio.create_task(issue_poller.run())
    schedule_trigger_scheduler = ScheduleTriggerScheduler(async_session)
    schedule_trigger_scheduler_task = asyncio.create_task(schedule_trigger_scheduler.run())
    worktree_cleanup = WorktreeCleanupScheduler(async_session)
    worktree_cleanup_task = asyncio.create_task(worktree_cleanup.run())
    yield
    logger.info("Shutting down worker")
    notification_dispatcher.stop()
    rules_dispatcher.stop()
    status_syncer.stop()
    scheduler.stop()
    cron_scheduler.stop()
    issue_poller.stop()
    schedule_trigger_scheduler.stop()
    worktree_cleanup.stop()
    worker_engine.stop()
    scheduler_task.cancel()
    cron_scheduler_task.cancel()
    issue_poller_task.cancel()
    schedule_trigger_scheduler_task.cancel()
    worktree_cleanup_task.cancel()
    worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker_task
        await scheduler_task
        await cron_scheduler_task
        await issue_poller_task
        await schedule_trigger_scheduler_task
        await worktree_cleanup_task
    await close_http_client()
    await queue_service.close()


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
app.include_router(docker_management_router, prefix="/api")
app.include_router(server_groups_router, prefix="/api")
app.include_router(server_projects_router, prefix="/api")
app.include_router(ollama_servers.router, prefix="/api")
app.include_router(llm_roles.router, prefix="/api")
app.include_router(ssh_keys_router, prefix="/api")
app.include_router(notification_channels.router, prefix="/api")
app.include_router(role_configs.router, prefix="/api")
app.include_router(workflow_templates.router, prefix="/api")
app.include_router(webhook_callbacks.router, prefix="/api")
app.include_router(worker_user_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(readiness_router, prefix="/api")
app.include_router(app_settings.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
app.include_router(git_connections.router, prefix="/api")
app.include_router(agent_stream.router, prefix="/api")
app.include_router(agent_control.router, prefix="/api")
app.include_router(agent_query.router, prefix="/api")
app.include_router(workspace_commands.router, prefix="/api")
app.include_router(agent_setup.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(local_terminals.router, prefix="/api")
app.include_router(platform_crons.router, prefix="/api")
app.include_router(scheduled_tasks.router, prefix="/api")
app.include_router(automation_rules.router, prefix="/api")
app.include_router(monitoring_rules.router, prefix="/api")
app.include_router(webhooks_monitoring.router, prefix="/api")
app.include_router(webhooks_linear.router, prefix="/api")
app.include_router(webhooks_pr_comment.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(webhooks_slack.router, prefix="/api")
app.include_router(webhooks_discord.router, prefix="/api")
app.include_router(ws.router)
app.include_router(ws_office.router)

# Mount MCP server for AI agent access (SSE transport)
app.mount("/mcp", get_mcp_app().http_app(transport="sse"))

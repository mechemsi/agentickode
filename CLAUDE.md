# CLAUDE.md

## Project Overview

Full-stack AI task automation platform: FastAPI backend + React/Vite frontend. The backend runs an 8-phase worker pipeline (workspace_setup → init → planning → coding → testing → reviewing → approval → finalization) that dispatches AI coding tasks to remote workspace servers, creates PRs, and gates on human approval.

## Key Features

- **Multi-provider git integration**: GitHub, Gitea, GitLab, Bitbucket (via GitProvider Protocol)
- **Pluggable AI agents**: Ollama, OpenHands, Claude CLI, custom agents (via RoleAdapter Protocol)
- **8-phase worker pipeline**: With per-phase status tracking, trigger modes (auto/manual/approval), comparison mode
- **Remote workspace servers**: SSH-based execution with worker user isolation, agent discovery/install
- **Workflow templates**: Label-based routing with per-phase agent/role configuration
- **Per-project instructions & secrets**: Global + phase-specific instructions, encrypted secrets with auto-injection
- **Real-time UI**: WebSocket log streaming, SSE dashboard updates, SSH terminal bridge (xterm.js)
- **Notifications**: Slack, Discord, Telegram, webhook callbacks
- **Webhook task sources**: Plane, GitHub, Gitea, GitLab issue events trigger runs automatically
- **Cost tracking**: Per-invocation token counting and cost estimation with analytics dashboard
- **Backup/export**: Full config export/import with optional AES encryption
- **GPU dashboard**: Ollama server GPU monitoring and model management
- **Role configs**: Customizable roles (planner, coder, reviewer) with per-agent prompt overrides
- **Comparison mode**: Run multiple agents in parallel, pick winner

## Project Structure

```
├── backend/
│   ├── api/                    # FastAPI route handlers
│   │   ├── runs.py             # Task run CRUD, approve/reject/retry/restart
│   │   ├── projects.py         # Project config CRUD, git URL parsing
│   │   ├── project_instructions.py # Per-project instructions & secrets
│   │   ├── webhooks.py         # Inbound webhooks (Plane, GitHub, Gitea, GitLab)
│   │   ├── webhooks_pr.py      # PR-related webhooks
│   │   ├── workflow_templates.py # Workflow template CRUD
│   │   ├── role_configs.py     # Role config CRUD with prompt overrides
│   │   ├── agents.py           # Agent settings & availability
│   │   ├── ollama_servers.py   # Ollama server management & GPU status
│   │   ├── notification_channels.py # Notification channel CRUD
│   │   ├── backup.py           # Export/import with encryption
│   │   ├── analytics.py        # Run analytics summary
│   │   ├── health.py           # System health checks
│   │   ├── ws.py               # WebSocket endpoints (logs, terminal, events)
│   │   ├── sse.py              # Server-Sent Events for run streaming
│   │   └── servers/            # Workspace server endpoints
│   │       ├── workspace_servers.py  # Server CRUD, test, setup
│   │       ├── agent_management.py   # Agent install/sync on servers
│   │       ├── worker_user.py        # Non-root worker user management
│   │       ├── git_access.py         # Git SSH key deploy & verification
│   │       ├── ssh_keys.py           # SSH key pair management
│   │       └── projects.py           # Discovered projects on server
│   ├── repositories/           # Repository pattern for DB access
│   ├── services/
│   │   ├── container.py        # ServiceContainer dataclass (DI)
│   │   ├── http_client.py      # Shared httpx.AsyncClient singleton
│   │   ├── role_resolver.py    # Role → provider → adapter resolution
│   │   ├── encryption.py       # AES encryption for secrets
│   │   ├── schedule.py         # Queue scheduling
│   │   ├── ollama_service.py   # Ollama LLM server integration
│   │   ├── openhands_service.py # OpenHands agent integration
│   │   ├── chromadb_service.py # ChromaDB vector storage (RAG)
│   │   ├── task_source_updater.py # Update issue trackers post-completion
│   │   ├── webhook_callback_service.py # Outbound webhook callbacks
│   │   ├── html_to_text.py     # HTML → plain text for issue descriptions
│   │   ├── json_extract.py     # JSON extraction from AI responses
│   │   ├── git/                # Git provider implementations
│   │   │   ├── protocol.py     # GitProvider Protocol definition
│   │   │   ├── github.py       # GitHub provider
│   │   │   ├── gitea.py        # Gitea provider
│   │   │   ├── gitlab.py       # GitLab provider
│   │   │   ├── bitbucket.py    # Bitbucket provider
│   │   │   ├── ops.py          # Git subprocess operations
│   │   │   ├── remote_ops.py   # Remote git operations via SSH
│   │   │   ├── access_service.py # Git SSH access configuration
│   │   │   ├── repo_info.py    # Repository info helpers
│   │   │   └── url_parser.py   # Git URL parsing
│   │   ├── adapters/           # AI agent adapters
│   │   │   ├── protocol.py     # RoleAdapter Protocol definition
│   │   │   ├── cli_adapter.py  # CLI agent adapter (Claude, etc.)
│   │   │   ├── cli_commands.py # CLI command builders
│   │   │   ├── cli_wrappers.py # CLI execution wrappers
│   │   │   ├── ollama_adapter.py # Ollama adapter
│   │   │   ├── openhands_adapter.py # OpenHands adapter
│   │   │   └── factory.py      # Adapter factory
│   │   ├── workspace/          # Workspace server management
│   │   │   ├── ssh_service.py  # SSH command execution
│   │   │   ├── setup_service.py # Async server setup
│   │   │   ├── agent_discovery.py # Discover agents on server
│   │   │   ├── agent_install_service.py # Install agents on server
│   │   │   ├── project_discovery.py # Discover projects on server
│   │   │   ├── worker_user_service.py # Non-root worker user setup
│   │   │   └── sandbox.py      # Sandbox management
│   │   ├── notifications/      # Notification dispatching
│   │   │   ├── dispatcher.py   # Route notifications to channels
│   │   │   ├── formatter.py    # Format notification messages
│   │   │   ├── slack.py        # Slack integration
│   │   │   ├── discord.py      # Discord integration
│   │   │   ├── telegram.py     # Telegram integration
│   │   │   └── webhook.py      # Generic webhook notifications
│   │   └── backup/             # Backup & export/import
│   │       ├── export_service.py # Export config to JSON
│   │       ├── import_service.py # Import config from JSON
│   │       ├── entity_registry.py # Entity serialization registry
│   │       ├── secret_handler.py # Encrypted backup handling
│   │       ├── serializers.py  # Entity serializers
│   │       └── schema_version.py # Backup schema versioning
│   ├── worker/
│   │   ├── engine.py           # WorkerEngine polling loop
│   │   ├── pipeline.py         # 8-phase pipeline sequencer
│   │   ├── broadcaster.py      # WebSocket/DB log broadcaster
│   │   └── phases/             # Individual phase implementations
│   │       ├── workspace_setup.py # Clone repo, create branch
│   │       ├── init_phase.py   # Analyze project, gather context
│   │       ├── planning.py     # Decompose task into subtasks
│   │       ├── coding.py       # Execute subtasks via AI agent
│   │       ├── testing.py      # Run test suite, report coverage
│   │       ├── reviewing.py    # AI code review
│   │       ├── approval.py     # Push branch, create PR, approval gate
│   │       ├── finalization.py # Notifications, cleanup, mark complete
│   │       ├── _helpers.py     # Shared phase utilities
│   │       ├── _prompt_resolver.py # Resolve prompts with instructions/secrets
│   │       ├── _comparison.py  # Multi-agent comparison logic
│   │       ├── _review_helpers.py # Review phase utilities
│   │       └── registry.py     # Phase registration
│   ├── config.py               # Pydantic Settings
│   ├── database.py             # SQLAlchemy async session
│   ├── dependencies.py         # FastAPI Depends() factories
│   ├── models.py               # SQLAlchemy models
│   ├── schemas.py              # Pydantic schemas
│   └── main.py                 # FastAPI app + lifespan
├── frontend/
│   └── src/
│       ├── pages/              # 10 page components
│       │   ├── Dashboard.tsx   # Run listing, stats, analytics charts, SSE updates
│       │   ├── NewRun.tsx      # Create run with per-phase agent overrides
│       │   ├── RunDetail.tsx   # Phase timeline, logs, approval, cost, terminal
│       │   ├── Projects.tsx    # Project CRUD with instructions tab
│       │   ├── WorkspaceServers.tsx # Server management, setup progress, agents
│       │   ├── AgentSettings.tsx # Agent configuration with env vars & CLI flags
│       │   ├── RoleConfigs.tsx # Role management with prompt overrides
│       │   ├── WorkflowTemplates.tsx # Workflow template management
│       │   ├── Settings.tsx    # Health, SSH keys, Ollama, backup, notifications
│       │   └── GpuDashboard.tsx # GPU monitoring, model management
│       ├── components/
│       │   ├── runs/           # Run-specific components (PhaseTimeline, LogViewer, ApprovalButtons, CostSummary, etc.)
│       │   ├── servers/        # Server components (GitAccessPanel, AgentManagementPanel, etc.)
│       │   ├── settings/       # Settings components (OllamaServerForm, BackupExport, NotificationSettings, etc.)
│       │   └── shared/         # Shared UI (Nav, StatusBadge, StatsBar, AnalyticsCharts, etc.)
│       ├── api/                # API client modules (runs, projects, servers, agents, workflows, health)
│       ├── types/              # TypeScript type definitions
│       └── __tests__/          # All frontend tests (Vitest + React Testing Library)
├── tests/
│   ├── conftest.py             # Shared fixtures (in-memory SQLite, mock services)
│   ├── unit/                   # Unit tests (88 files)
│   └── integration/            # Integration tests (17 files)
├── alembic/                    # Database migrations (17 versions)
├── .github/workflows/          # CI + dependency audit
└── docs/
    ├── WORKER_PIPELINE.md      # Complete worker pipeline technical reference
    ├── guides/                 # Architecture & operations guides
    │   ├── 09-webhook-setup.md # Webhook setup for GitHub, GitLab, Gitea, Plane
    │   └── decisions/          # Architecture decision records
    └── plans/                  # Feature implementation plans
```

## Development Environment

**All commands must run inside Docker containers.** Never run tests, lints, type checks, or build commands on the host machine. Use `docker compose -f docker-compose.dev.yml` for the dev environment.

```bash
# Start dev environment
docker compose -f docker-compose.dev.yml up -d

# Rebuild after Dockerfile changes
docker compose -f docker-compose.dev.yml up -d --build
```

## Commands

All commands below use `docker compose -f docker-compose.dev.yml exec`. If the dev containers are already running, you may use the short form `docker compose exec`.

### Backend

```bash
# Run all tests
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -v

# Run tests with coverage
docker compose -f docker-compose.dev.yml exec backend pytest tests/ --cov=backend --cov-report=term-missing

# Run specific test file
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_pipeline.py -v

# Lint check
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/

# Lint auto-fix
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/ --fix

# Format
docker compose -f docker-compose.dev.yml exec backend ruff format backend/ tests/

# Type check
docker compose -f docker-compose.dev.yml exec backend pyright backend/
```

### Frontend

```bash
# Run all tests
docker compose -f docker-compose.dev.yml exec frontend npm test

# Run tests with coverage
docker compose -f docker-compose.dev.yml exec frontend npm run test:coverage

# Lint check
docker compose -f docker-compose.dev.yml exec frontend npm run lint

# Lint auto-fix
docker compose -f docker-compose.dev.yml exec frontend npm run lint:fix
```

## Architecture

Workspace servers are REMOTE machines accessed via SSH, not local subprocesses. Never use local subprocess calls for workspace operations. All workspace interactions go through `SSHService`.

## Architecture Rules

### SOLID Principles

1. **GitProvider Protocol**: Always use the `GitProvider` Protocol for git operations (create_repo, create_pr, merge_pr). Never call Gitea/GitHub APIs directly. Use `get_git_provider(provider_name, client)` factory.

2. **RoleAdapter Protocol**: Always use the `RoleAdapter` Protocol for AI agent interactions. Never call agent APIs directly. Use `RoleResolver` to map roles to providers.

3. **Service Classes**: Always use injectable service classes (`OllamaService`, `OpenHandsService`, `ChromaDBService`). Never create `httpx.AsyncClient()` in service functions. Services receive their client via constructor.

4. **ServiceContainer**: Worker phases receive `services: ServiceContainer` parameter. Never import service modules directly in phases.

5. **Repository Pattern**: Always use `TaskRunRepository` and `ProjectConfigRepository` for DB access. No inline SQLAlchemy queries in route handlers.

6. **Shared HTTP Client**: Use `get_http_client()` from `backend/services/http_client.py`. Never create standalone httpx clients.

### Code Quality

- Max 200 lines per file. Split if larger.
- No large singletons. Use dependency injection.
- All new features must have tests. Maintain 70%+ coverage.
- Follow existing patterns: async/await, Pydantic schemas, SQLAlchemy models.

### License Headers

All source files **must** include the license header as the first lines. CI enforces this on every PR and push to main.

**Python files** (`.py` in `backend/` and `tests/`):
```python
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com
```

**TypeScript files** (`.ts`/`.tsx` in `frontend/src/`):
```typescript
// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com
```

When creating new files, always add the appropriate header before any imports or code.

### After Every Backend Edit

**Default: targeted runs on edited files only** to save context and time.

```bash
# Lint/format ONLY the edited files
docker compose -f docker-compose.dev.yml exec backend ruff check backend/path/to/edited_file.py --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/path/to/edited_file.py

# Type check the edited file
docker compose -f docker-compose.dev.yml exec backend pyright backend/path/to/edited_file.py

# Run ONLY the related test file(s)
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_edited_module.py -x -v
```

**Full suite — only run when:**
- Changing models, schemas, or shared utilities that affect many modules
- Editing conftest.py, config.py, database.py, or dependencies.py
- Before committing / finishing a task
- Refactoring imports or moving files

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/ --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/ tests/
docker compose -f docker-compose.dev.yml exec backend pyright backend/
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -x -v
```

### After Every Frontend Edit

**Default: targeted runs on edited files only.**

```bash
# Lint only the edited file
docker compose -f docker-compose.dev.yml exec frontend npx eslint src/path/to/EditedFile.tsx --fix

# Run only the related test
docker compose -f docker-compose.dev.yml exec frontend npx vitest run src/__tests__/EditedFile.test.tsx
```

**Full suite — only run when:**
- Changing types.ts, api.ts, or shared components used across pages
- Before committing / finishing a task

```bash
docker compose -f docker-compose.dev.yml exec frontend npm run lint
docker compose -f docker-compose.dev.yml exec frontend npm test
```

### Testing Conventions

- Backend tests use in-memory SQLite with JSONB→JSON mapping (see `conftest.py`)
- Use `mock_services` fixture for mocked `ServiceContainer`
- Use `make_task_run` factory fixture for creating test `TaskRun` records
- Frontend tests use Vitest + React Testing Library
- Mock API calls with `vi.mock("../api", ...)`
- Wrap routed components in `<MemoryRouter>`

### Worker Pipeline

- 8 phases execute sequentially: workspace_setup → init → planning → coding → testing → reviewing → approval → finalization
- The approval phase returns `"awaiting"` to park the run for human review
- After approval, the engine resumes from the finalization phase
- Phase functions signature: `async def run(task_run, session, services) -> None | str`
- Trigger modes: `auto` (default), `wait_for_trigger` (manual advance), `wait_for_approval`
- Comparison mode: run multiple agents in parallel, user picks winner

## Workflow Rules

When asked to create a plan, write it to a file immediately and do NOT attempt to exit plan mode or wait for approval before starting implementation unless explicitly told to only plan. Bias toward action over planning.

## CI/CD

GitHub Actions workflow files must be placed at the REPOSITORY ROOT under `.github/workflows/`, not inside subdirectories like `autodev-app/.github/workflows/`.

## Docker & Infrastructure

When migrating or restructuring projects (e.g., promoting subdirectory to root), always preserve: 1) `.env` files (copy or recreate), 2) Docker volume names/references to avoid losing database data, 3) Verify existing services still connect after network changes.

## Development Practices

After making changes, always verify they work end-to-end rather than assuming success. For long debugging chains, check the actual logs at each step rather than making multiple speculative fixes.

## Documentation

- `docs/WORKER_PIPELINE.md` — complete worker pipeline technical reference
- `docs/guides/09-webhook-setup.md` — webhook setup for GitHub, GitLab, Gitea, Plane
- `docs/guides/decisions/` — architecture decision records

# CLAUDE.md

## Overview

Full-stack AI task automation platform: FastAPI backend + React/Vite frontend. The backend dispatches AI coding tasks to workspace servers, creates PRs, and gates on human approval. The execution model is moving from a configurable multi-step **worker pipeline** (the legacy phases workspace_setup → init → planning → coding → testing → reviewing → approval → finalization, still the default) to **agentic flow prompts** — a single agent call given a prompt + fetched data ([ADR-009](claudedocs/decisions/009-flow-prompts.md)), gated behind `FLOW_PROMPTS_ENABLED`.

## Tech Stack
- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Pydantic, Alembic
- **Frontend**: TypeScript, React 18, Vite, React Router
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Testing**: pytest (backend), Vitest + React Testing Library (frontend)
- **Linting**: ruff (Python), ESLint (TypeScript)
- **Type checking**: pyright (Python), TypeScript compiler
- **Infrastructure**: Docker Compose, SSH-based remote workspaces

## Code Style
- Follow rules in `.claude/rules/code-style.md`
- Follow API conventions in `.claude/rules/api-conventions.md`
- All new features must have tests per `.claude/rules/testing.md`
- Follow documentation conventions in `.claude/rules/documentation.md`

## Key Features

- **Multi-provider git integration**: GitHub, Gitea, GitLab, Bitbucket (via GitProvider Protocol)
- **Pluggable AI agents**: Ollama, OpenHands, Claude CLI, custom agents (via the `RoleAdapter` adapter protocol)
- **Worker pipeline**: Configurable multi-step run with per-step status tracking and trigger modes (auto/manual/approval)
- **Flow prompts (ADR-009)**: Single-agent-call runs (prompt + auto-fetched data) — `FLOW_PROMPTS_ENABLED`; replacing the pipeline
- **Remote workspace servers**: SSH-based execution with worker user isolation, agent discovery/install
- **Workflow templates**: Label-based routing with per-step agent selection (being superseded by flow prompts)
- **Per-project instructions & secrets**: Global + phase-specific instructions, encrypted secrets with auto-injection
- **Real-time UI**: WebSocket log streaming, SSE dashboard updates, SSH terminal bridge (xterm.js)
- **Notifications**: Slack, Discord, Telegram, webhook callbacks
- **Webhook task sources**: Plane, GitHub, Gitea, GitLab issue events trigger runs automatically
- **Cost tracking**: Per-invocation token counting and cost estimation with analytics dashboard
- **Backup/export**: Full config export/import with optional AES encryption
- **GPU dashboard**: Ollama server GPU monitoring and model management
- **Direct agent selection**: Each step names the agent (or uses the project/global default) via `AgentResolver` — no role indirection ([ADR-008](claudedocs/decisions/008-direct-agent-selection.md))
- **Platform crons**: Self-scheduling agent loop for autonomous monitoring
- **Session resume**: Claude conversation state resumption with `--resume` flag

## Project Structure

```
├── backend/
│   ├── api/                    # FastAPI route handlers
│   ├── repositories/           # Repository pattern for DB access
│   ├── services/               # Business logic, integrations
│   │   ├── git/                # Git provider implementations (Protocol)
│   │   ├── adapters/           # AI agent adapters (Protocol)
│   │   ├── workspace/          # SSH workspace server management
│   │   ├── notifications/      # Notification dispatching
│   │   └── backup/             # Backup & export/import
│   ├── worker/                 # Worker engine: phase pipeline + flow-prompt executor
│   │   └── phases/             # Individual phase implementations
│   ├── config.py               # Pydantic Settings
│   ├── database.py             # SQLAlchemy async session
│   ├── models.py               # SQLAlchemy models
│   ├── schemas.py              # Pydantic schemas
│   └── main.py                 # FastAPI app + lifespan
├── frontend/
│   └── src/
│       ├── pages/              # Page components (Dashboard, RunDetail, etc.)
│       ├── components/         # Shared + domain-specific components
│       ├── api/                # API client modules
│       ├── types/              # TypeScript type definitions
│       └── __tests__/          # Frontend tests
├── tests/
│   ├── unit/                   # Backend unit tests
│   └── integration/            # Backend integration tests
├── alembic/                    # Database migrations
├── claudedocs/                 # Project documentation (see below)
│   ├── INDEX.md                # Master index — read this first
│   ├── plans/                  # Feature specs before implementation
│   ├── implementations/       # What was built and how it works
│   ├── decisions/              # Architecture Decision Records (ADRs)
│   └── runbooks/               # Step-by-step operational guides
├── .claude/                    # Claude Code configuration
│   ├── settings.json           # Shared permissions and rules
│   ├── rules/                  # Modular coding standards
│   ├── commands/               # Custom slash commands (/review, /deploy, /fix-issue)
│   ├── agents/                 # Subagent personas (code-reviewer, security-analyst)
│   └── skills/                 # Auto-invoked workflows (deploy, security-review)
├── .github/workflows/          # CI + dependency audit
└── docs/                       # Legacy docs + implementation log
```

## Development Environment

**All commands must run inside Docker containers.** Never run tests, lints, type checks, or build commands on the host machine.

```bash
# Start dev environment
docker compose -f docker-compose.dev.yml up -d

# Rebuild after Dockerfile changes
docker compose -f docker-compose.dev.yml up -d --build
```

## Commands

All commands below use `docker compose -f docker-compose.dev.yml exec`.

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

## Architecture Rules

### SOLID Principles

1. **GitProvider Protocol**: Use `get_git_provider(provider_name, client)` factory. Never call git APIs directly.
2. **Agent selection**: Use `AgentResolver` to resolve the agent (per-step `agent` field → project/global default) and the `RoleAdapter` adapter protocol to talk to it. Never call agent APIs directly.
3. **Service Classes**: Injectable via constructor (`OllamaService`, `OpenHandsService`, `ChromaDBService`). Never create `httpx.AsyncClient()` in service functions.
4. **ServiceContainer**: Worker phases receive `services: ServiceContainer`. Never import service modules directly in phases.
5. **Repository Pattern**: Use `TaskRunRepository`, `ProjectConfigRepository` for DB access. No inline SQLAlchemy in route handlers.
6. **Shared HTTP Client**: Use `get_http_client()` from `backend/services/http_client.py`.

### Remote Architecture

Workspace servers are REMOTE machines accessed via SSH, not local subprocesses. All workspace interactions go through `SSHService`.

### Code Quality

- Max 200 lines per file. Split if larger.
- No large singletons. Use dependency injection.
- All new features must have tests. Maintain 70%+ coverage.
- Follow existing patterns: async/await, Pydantic schemas, SQLAlchemy models.

### License Headers

All source files **must** include the license header. CI enforces this.

**Python** (`.py` in `backend/` and `tests/`):
```python
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com
```

**TypeScript** (`.ts`/`.tsx` in `frontend/src/`):
```typescript
// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com
```

### After Every Backend Edit

**Default: targeted runs on edited files only.**

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/path/to/edited_file.py --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/path/to/edited_file.py
docker compose -f docker-compose.dev.yml exec backend pyright backend/path/to/edited_file.py
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_edited_module.py -x -v
```

**Full suite — only when:** changing models/schemas/shared utils, editing conftest/config/database/dependencies, before committing.

### After Every Frontend Edit

**Default: targeted runs on edited files only.**

```bash
docker compose -f docker-compose.dev.yml exec frontend npx eslint src/path/to/EditedFile.tsx --fix
docker compose -f docker-compose.dev.yml exec frontend npx vitest run src/__tests__/EditedFile.test.tsx
```

**Full suite — only when:** changing types/api/shared components, before committing.

### Testing Conventions

- Backend: in-memory SQLite with JSONB→JSON mapping (see `conftest.py`)
- Use `mock_services` fixture for mocked `ServiceContainer`
- Use `make_task_run` factory for test `TaskRun` records
- Frontend: Vitest + React Testing Library, mock API with `vi.mock("../api", ...)`
- Wrap routed components in `<MemoryRouter>`

### Worker Pipeline (legacy) + Flow Prompts (ADR-009)

- **Pipeline (default)**: legacy phases workspace_setup → init → planning → coding → testing → reviewing → approval → finalization, dispatched from a workflow template.
- **Flow prompts (`FLOW_PROMPTS_ENABLED`)**: a run bound to a `flow_prompt_id` skips the phase loop and runs `workspace_setup`/`init` → fetch the flow's data → **a single agent call** → `finalization` (`backend/worker/flow/executor.py`). The agent's response is the run outcome.
- Approval phase returns `"awaiting"` to park run for human review
- Phase signature: `async def run(task_run, session, services) -> None | str`
- Trigger modes: `auto`, `wait_for_trigger`, `wait_for_approval`

## Documentation Workflow

Claude must keep `claudedocs/` up to date as part of the development process:

### Before starting a feature
1. Check `claudedocs/INDEX.md` for existing context
2. Create a plan doc in `claudedocs/plans/` if one doesn't exist
3. If a significant technical choice is being made, create an ADR in `claudedocs/decisions/`

### After completing a feature
1. Create or update an implementation doc in `claudedocs/implementations/`
2. Update the plan doc status from `planned` to `implemented`
3. Update `claudedocs/INDEX.md` with any new or changed docs

### When a process is repeated
1. If you explain the same steps twice, create a runbook in `claudedocs/runbooks/`
2. Add it to `claudedocs/INDEX.md`

### Rules
- Always read `claudedocs/INDEX.md` first when starting work on a feature
- Never leave INDEX.md out of sync — update it whenever a doc is added or changes status
- Use YAML frontmatter in every doc (`title`, `status`, `date`, `related`)

## Git Conventions
- Branch naming: `feat/`, `fix/`, `chore/`, `docs/`
- Commit style: Conventional Commits (`feat: add login page`)
- Never commit directly to `main` — always open a PR (unless explicitly told otherwise)

## CI/CD

GitHub Actions workflow files at `.github/workflows/` (repository root).

## Docker & Infrastructure

When migrating or restructuring, preserve: 1) `.env` files, 2) Docker volume names, 3) Verify services connect after network changes.

## Development Practices

After making changes, always verify end-to-end. For long debugging chains, check actual logs at each step.

## Implementation Log

After completing significant work, append to `docs/IMPLEMENTATION_LOG.md` with: date, version, summary, files changed, tests, commit hash.

## Lessons

After any comments from me, add entry to `tasks/lessons.md`: date, what went wrong, rule for next time. Read this before doing anything.

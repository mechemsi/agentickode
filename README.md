<div align="center">

# AgenticKode

### Composable AI workflows triggered by your tools

**Compose `bash` and `agent` steps into workflows that run when an issue is filed, a webhook fires, or a cron tick lands. AgenticKode handles the workspace, the prompt rendering, the retries, and the human-approval gate. Self-hosted, pluggable, and honest about what your agent actually does.**

<br>

[![CI](https://github.com/mechemsi/agentickode/actions/workflows/ci.yml/badge.svg)](https://github.com/mechemsi/agentickode/actions/workflows/ci.yml)
[![Dependency Audit](https://github.com/mechemsi/agentickode/actions/workflows/dependency-audit.yml/badge.svg)](https://github.com/mechemsi/agentickode/actions/workflows/dependency-audit.yml)
[![License Check](https://github.com/mechemsi/agentickode/actions/workflows/license-check.yml/badge.svg)](https://github.com/mechemsi/agentickode/actions/workflows/license-check.yml)
[![License: AGPLv3](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)
![Node 22](https://img.shields.io/badge/node-22-green.svg)
![React 18](https://img.shields.io/badge/react-18-61dafb.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)
![TypeScript 5.7](https://img.shields.io/badge/TypeScript-5.7-3178c6.svg)
![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791.svg)
![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

</div>

---

<div align="center">

<img src="docs/screenshots/demo.gif" alt="AgenticKode Demo" width="100%">

*Full UI walkthrough — Dashboard, Run Detail, Projects, Servers, Agents, Workflows, Settings*

</div>

## Why AgenticKode?

Most AI coding tools are chat-based — you type prompts, copy-paste code, manually test, and commit. **AgenticKode eliminates all of that.** It connects directly to your issue tracker and git provider, runs AI agents on remote workspace servers, and delivers ready-to-review pull requests.

**What makes AgenticKode different:**

- **Composable `bash` + `agent` steps with first-class triggers** — Workflows are arrays of steps. Each step is either a shell command on the workspace or an agent invocation with a rendered prompt. Both share the same rules (timeout, retry, failure_mode, trigger_mode). The legacy 8-phase shape is preserved as one of several seeded templates ([ADR-007](claudedocs/decisions/007-composable-step-workflows.md)).
- **Trigger-driven, not just manual** — Templates declare what fires them: GitHub/Gitea/GitLab/Plane/Notion webhooks, schedule (cron), labels, PR events, or manual.
- **Self-hosted & private** — Your code never leaves your infrastructure. Run it on your own servers with your own models.
- **7+ AI agents** — Claude CLI, Codex, Gemini, Aider, OpenCode, Kimi, Copilot, Ollama, OpenHands — all with auto-install. Mix and match per step.
- **Smart workspaces** — Multi-server assignment, server groups, automatic load balancing, parallel runs, persistent CLI sessions with tmux, optional per-run worktrees.
- **Human-in-the-loop where it matters** — Any step can be marked `trigger_mode: wait_for_approval` and park the run for human review. Otherwise the workflow runs end-to-end.
- **Multi-agent comparison** — Run the same workflow with different agents in parallel, compare the results, pick the winner.
- **Works with your stack** — GitHub, GitLab, Gitea, Bitbucket. Plane, GitHub Issues, GitLab Issues, Notion. Slack, Discord, Telegram notifications.

## How It Works

Every task runs a **workflow** — a user-composed sequence of `bash` and `agent` steps. Two built-in steps (`workspace_setup`, `init`) always run first; the rest is defined per-template and routed to the worker by triggers.

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐
│  Trigger    │ -> │  Template    │ -> │  Workspace   │ -> │  Steps               │
│  matcher    │    │  (steps[])   │    │  setup+init  │    │  bash | agent | ...  │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────────────┘
   ^                                                              │
   │   webhook · schedule · label · PR event · manual             ▼
   │                                                       PR · message · done
   └─── GitHub · Gitea · GitLab · Plane · Notion · cron ──────────┘
```

| Concept | What it is | Configured per |
|---------|------------|----------------|
| **Trigger** | Declarative rule that fires a workflow when something happens | Template |
| **Workspace strategy** | `shared_clone` (default) or `worktree` (per-run, timestamped) | Template / project |
| **Step kind** | `bash`, `agent`, or `legacy_phase` — what the step actually does | Step |
| **Step rules** | `timeout_seconds`, `retry_count`, `failure_mode`, `trigger_mode` | Step |
| **Templating** | `{{run.title}}`, `{{run.description}}`, `{{steps.NAME.field}}` available in any string field | Step |

### Step Kinds

| Kind | What it does | Typical use |
|------|--------------|-------------|
| **`bash`** | Runs a shell command on the workspace server via `CommandExecutor`. Captures stdout/stderr/exit. | Build, test, lint, `gh pr create`, anything CLI. |
| **`agent`** | Invokes a role (planner / coder / reviewer / custom) through `RoleResolver` with a rendered prompt. Supports `mode: generate` or `mode: task`, session continuity (`session_id`, `new_session`), and per-step `agent_override`. | Decompose work, write code, review a diff, summarize logs, anything LLM-shaped. |
| **`legacy_phase`** | Invokes one of the original domain modules (`planning`, `coding`, `testing`, `reviewing`, `approval`, `finalization`, `pr_fetch`, `task_creation`, `agent_loop`). Kept indefinitely for back-compat. | The `default` workflow template uses this kind for every step — existing templates keep running unchanged. |

### Triggers

A template's `triggers[]` array declares when the workflow auto-fires:

| Type | Fires when | Example |
|------|------------|---------|
| **`label`** | An incoming task carries a matching label | `{type: label, value: bug}` |
| **`issue_event`** | A webhook reports an issue lifecycle event | `{type: issue_event, action: opened}` |
| **`pr_event`** | A webhook reports a PR event | `{type: pr_event, action: review_requested}` |
| **`schedule`** | A cron tick lands | `{type: schedule, cron: "0 * * * *"}` |
| **`manual`** | A user (or the API) creates a run against this template | `{type: manual}` |

Webhooks from GitHub, Gitea, GitLab, Plane, and Notion all funnel through a single `TriggerMatcher` service that routes the incoming event to the template whose triggers match.

<div align="center">

<img src="docs/screenshots/run-detail-top.png" alt="Run Detail - Step Timeline" width="100%">

*Run detail view with step timeline, task metadata, PR link, and action buttons*

</div>

## Features

### Supported AI Agents

AgenticKode doesn't lock you into one AI provider. The **RoleAdapter Protocol** lets you plug in any AI agent — and AgenticKode can **auto-install** them on your workspace servers.

<img src="docs/screenshots/agents.png" alt="Agent Settings" width="100%">

#### CLI Agents

These run directly on your workspace servers via SSH. AgenticKode discovers, installs, and manages them automatically.

| Agent | Provider | Session Support | Auto-Install | Best For |
|-------|----------|:--------------:|:------------:|----------|
| **[Claude CLI](https://docs.anthropic.com/en/docs/claude-code)** | Anthropic | Yes | Yes | High-quality code generation with session continuity. Supports resuming previous sessions for multi-step tasks. |
| **[Codex CLI](https://github.com/openai/codex)** | OpenAI | — | Yes | OpenAI-powered autonomous coding agent. |
| **[Gemini CLI](https://github.com/google-gemini/gemini-cli)** | Google | — | Yes | Google's Gemini models for code generation. |
| **[Aider](https://aider.chat)** | Multi-provider | — | Yes | AI pair programming tool. Works with OpenAI, Anthropic, local models, and many others. |
| **[OpenCode](https://opencode.ai)** | Multi-provider | — | Yes | Terminal-based AI coding assistant. |
| **[Kimi CLI](https://kimi.ai)** | Moonshot | — | Yes | Moonshot's Kimi models for code tasks. |
| **[GitHub Copilot CLI](https://github.com/features/copilot)** | GitHub/Microsoft | — | Yes | GitHub Copilot in autopilot mode for terminal-based coding. |

#### API-Based Agents

These connect over HTTP to a running service. No workspace server SSH needed.

| Agent | Type | Session Support | Auto-Install | Best For |
|-------|------|:--------------:|:------------:|----------|
| **[OpenHands](https://github.com/All-Hands-AI/OpenHands)** | Autonomous agent | — | Docker pull | Complex multi-file autonomous coding with sandboxed execution. |

#### LLM Providers (for Planning & Reviewing)

These are used for text generation roles (planner, reviewer) rather than direct code execution.

| Provider | Models | GPU Dashboard | Best For |
|----------|--------|:------------:|----------|
| **[Ollama](https://ollama.ai)** | Any GGUF model (Qwen, DeepSeek, Llama, Mistral, etc.) | Yes | Self-hosted LLM inference. Zero API costs. Full privacy. Manage models and monitor GPU usage from the AgenticKode dashboard. |

#### Bring Your Own Agent

AgenticKode's plugin architecture makes it easy to add new agents:

- **CLI agents**: Add a command template to `AGENT_COMMANDS` dict — define `generate`, `task`, and `check` commands. AgenticKode handles SSH execution, output capture, and error handling.
- **API agents**: Implement the `RoleAdapter` Protocol (4 methods: `provider_name`, `generate`, `run_task`, `is_available`) and register in the `AdapterFactory`.
- **Per-agent config**: Each agent has configurable timeouts, retry limits, environment variables, and CLI flags — all manageable from the UI.

#### Mix & Match Per Step

Use different agents for different steps in the same workflow:

```
plan    →  agent[role: planner]   →  Ollama (qwen2.5-coder:32b)   # Fast, free, local
code    →  agent[role: coder]     →  Claude CLI                    # Best code quality
review  →  agent[role: reviewer]  →  Ollama (qwen2.5-coder:14b)   # Cost-effective review
```

**Workflow templates**: Create templates that auto-fire on triggers (`label: bug`, `issue_event: opened`, `schedule: "0 * * * *"`, etc.). Each step inside a template can override the agent, prompt, and timeout independently. See [ADR-007](claudedocs/decisions/007-composable-step-workflows.md) for the design rationale.

<img src="docs/screenshots/workflows.png" alt="Workflow Templates" width="100%">

### Git Provider Support

| Provider | PRs | Webhooks | Issue Updates |
|----------|-----|----------|---------------|
| GitHub | Yes | Yes | Yes |
| GitLab | Yes | Yes | Yes |
| Gitea | Yes | Yes | Yes |
| Bitbucket | Yes | — | — |

**Webhook sources**: Plane, GitHub, Gitea, and GitLab issue events can automatically trigger AgenticKode runs.

### Workspace Management

AgenticKode runs AI agents on **remote workspace servers** — dedicated machines accessed via SSH:

- **Multi-workspace assignment**: Assign multiple servers to a project with automatic load balancing
- **Server groups**: Organize workspace servers into logical groups for easier management
- **Parallel runs**: Run multiple tasks concurrently across different workspaces for the same project
- **Worker user isolation**: Code execution runs under a non-root user for security
- **Agent discovery & sync**: AgenticKode finds and manages installed agents on your servers
- **SSH terminal bridge**: Jump into any server from the UI via xterm.js with user selection
- **Docker management**: Monitor and manage Docker containers on workspace servers
- **Per-server git connections**: Configure git tokens per server and project

<img src="docs/screenshots/workspace-servers.png" alt="Workspace Servers" width="100%">

### Persistent CLI Sessions

Manage long-running AI agent sessions with tmux-based persistence:

- **Attach & detach**: Connect to running agent sessions, detach without stopping them
- **Session management**: Create, list, kill sessions from the UI
- **Chat interface**: Interact with AI agents through a built-in chat UI
- **Health monitoring**: Automatic session health checks with status tracking
- **Cross-server**: Sessions run on remote workspace servers via SSH

### Autonomous Mode

For tasks that don't need step-by-step control:

- **Context builder**: Agent analyzes project structure and relevant files before starting
- **Configurable autonomy**: Set autonomy levels — how much freedom the agent gets
- **Direct PR creation**: Agents can create pull requests directly, skipping the approval push step
- **PR status monitoring**: Hourly checks auto-approve or reject runs based on PR state

### IDE Integration

Open any project on your workspace servers directly in your IDE — one click from the AgenticKode UI.

#### VS Code Remote SSH

Click **"VS Code"** next to any project to open it in VS Code via the [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode.remote-ssh) extension:

```
vscode://vscode-remote/ssh-remote+coder@your-server/home/coder/projects/your-repo
```

AgenticKode generates the correct `vscode://` URI with:
- Automatic worker user detection (uses `coder` if configured, falls back to `root`)
- SSH config snippet generation for non-standard ports
- Direct deep-link to the project directory on the remote server

#### JetBrains Gateway

Click **"JetBrains"** to open a picker with all supported IDEs via [JetBrains Gateway](https://www.jetbrains.com/remote-development/gateway/):

| IDE | Supported |
|-----|:---------:|
| IntelliJ IDEA | Yes |
| PyCharm | Yes |
| WebStorm | Yes |
| GoLand | Yes |
| PhpStorm | Yes |
| RubyMine | Yes |
| Rider | Yes |
| CLion | Yes |

AgenticKode generates `jetbrains-gateway://` URIs with SSH connection details, so Gateway connects directly to the right server, user, and project path.

#### SSH Terminal (xterm.js)

For quick access without leaving the browser, use the built-in **SSH terminal** — a full xterm.js terminal embedded in the AgenticKode UI that connects to your workspace server via WebSocket. Available from both the server management page and individual run detail pages.

### Ollama Server Management & GPU Dashboard

AgenticKode includes a dedicated dashboard for managing your Ollama LLM servers:

#### Multi-Server Management
- **Register multiple Ollama servers** — connect to Ollama instances across your infrastructure
- **Health monitoring** — automatic status checks with last-seen timestamps
- **Model discovery** — auto-fetch available models from each server
- **Role assignment** — assign specific servers and models to roles (planner, coder, reviewer, custom)

#### GPU Monitoring
- **Real-time GPU status** — see VRAM usage per loaded model across all servers
- **VRAM split visualization** — see how much of each model is in GPU vs CPU memory
- **Running model list** — view all currently loaded models with memory footprint and expiry timers

#### Model Control
- **Preload models** — load models into GPU memory before workflow runs to eliminate cold-start delays
- **Unload models** — free GPU memory by unloading models you're not using
- **Keep-alive configuration** — control how long models stay loaded after last use

This lets you optimize GPU utilization across multiple servers — preload your coding model before a batch of runs, unload the planning model when you're done, and monitor everything from one dashboard.

### Real-Time Monitoring

- **Live log streaming** via WebSocket — see exactly what the AI agent is doing
- **Step timeline** — clickable visualization of workflow progress
- **Cost tracking** — per-invocation token counting and cost estimation
- **Analytics dashboard** — 14-day rolling charts of runs, costs, and success rates
- **Health monitoring** — database, Redis, Ollama, OpenHands status at a glance

### Project Configuration

- **Per-project instructions** — Global prompts plus step-specific instructions (e.g., "always use pytest", "follow our naming conventions")
- **Encrypted secrets** — Store API keys and credentials that get injected into agent prompts securely
- **Comparison mode** — Run multiple agents on the same task, compare outputs side-by-side, pick the best result

### Notifications & Integrations

| Channel | Status Updates | Approval Requests | Completion |
|---------|---------------|-------------------|------------|
| Slack | Yes | Yes | Yes |
| Discord | Yes | Yes | Yes |
| Telegram | Yes | Yes | Yes |
| Webhooks | Yes | Yes | Yes |

### Operations

- **Backup & restore** — Full config export/import with optional AES encryption
- **GPU dashboard** — Monitor Ollama server GPU utilization and manage models
- **Queue scheduling** — Control concurrent run limits and prioritization
- **Retry & restart** — Retry failed steps or restart entire runs

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    Frontend                       │
│         React 18 + TypeScript + Vite              │
│    Dashboard, Run Detail, Projects, Servers       │
│         WebSocket + SSE live updates              │
├─────────────────────────────────────────────────┤
│                   FastAPI Backend                  │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ REST API    │  │ Worker Engine│  │ Services│  │
│  │ Routes      │  │ Step runner  │  │         │  │
│  │ WebSocket   │  │ (bash/agent/ │  │ Git     │  │
│  │ SSE         │  │  legacy)     │  │ Agents  │  │
│  │ Webhooks ─→ │  │ Trigger      │  │ SSH     │  │
│  │  Trigger    │  │ matcher      │  │ Notify  │  │
│  │  matcher    │  │ Broadcaster  │  │         │  │
│  └─────────────┘  └──────────────┘  └─────────┘ │
├──────────────────┬──────────────────────────────┤
│   PostgreSQL 16  │         Redis 7               │
│   JSONB storage  │     Cache & queues            │
├──────────────────┴──────────────────────────────┤
│              Workspace Servers (SSH)              │
│    ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐      │
│    │Ollama│  │Claude│  │Open  │  │Custom│       │
│    │      │  │CLI   │  │Hands │  │Agent │       │
│    └──────┘  └──────┘  └──────┘  └──────┘      │
└─────────────────────────────────────────────────┘
```

### Design Principles

- **Protocol-driven**: `GitProvider` and `RoleAdapter` Protocols make everything pluggable
- **Repository pattern**: Clean separation between API routes and database access
- **Dependency injection**: `ServiceContainer` provides services to worker steps
- **Async-first**: Built on async SQLAlchemy, httpx, and FastAPI for high concurrency

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A git provider account (GitHub, GitLab, Gitea, or Bitbucket)
- At least one AI agent (Ollama for local, or API keys for cloud agents)

### Installation

```bash
# Clone the repository
git clone https://github.com/mechemsi/agentickode.git
cd agentickode

# Copy and configure environment
cp .env.example .env
# Edit .env with your git provider tokens and agent URLs

# Start AgenticKode
docker compose -f docker-compose.dev.yml up -d
```

### Access

| Service | URL |
|---------|-----|
| **UI** | http://localhost:5173 |
| **API** | http://localhost:8000 |
| **API Docs** | http://localhost:8000/docs |

### First Run

1. **Add a workspace server** — Go to Servers, add your remote machine's SSH details
2. **Create a project** — Add your repo URL and git provider credentials
3. **Create a run** — Pick a project, describe the task (or connect webhooks for automatic triggering)
4. **Watch it work** — Follow the live workflow, review the plan, approve the PR

## Configuration

<img src="docs/screenshots/settings.png" alt="Settings" width="100%">

*Default agents, queue schedule, Ollama servers, notifications, backup/import, SSH keys*

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://agentickode:agentickode@postgres:5432/agentickode` |
| `OLLAMA_URL` | Ollama server URL | `http://localhost:11434` |
| `OPENHANDS_URL` | OpenHands server URL | `http://localhost:3000` |
| `GITHUB_TOKEN` | GitHub personal access token | — |
| `GITEA_URL` / `GITEA_TOKEN` | Gitea server URL and token | — |
| `GITLAB_TOKEN` | GitLab personal access token | — |
| `MAX_CONCURRENT_RUNS` | Max parallel workflow runs | `3` |
| `APPROVAL_TIMEOUT_HOURS` | Hours before approval times out | `24` |
| `ENCRYPTION_KEY` | AES key for backup encryption | — |

See [`.env.example`](.env.example) for the full list.

### Webhook Setup

AgenticKode can automatically start runs when issues are created in your tracker:

- **GitHub** — Repository webhook → `POST /api/webhooks/github`
- **GitLab** — Project webhook → `POST /api/webhooks/gitlab`
- **Gitea** — Repository webhook → `POST /api/webhooks/gitea`
- **Plane** — Project webhook → `POST /api/webhooks/plane`

See the [Webhook Setup Guide](docs/guides/09-webhook-setup.md) for detailed instructions.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Pydantic v2 |
| Frontend | React 18, TypeScript 5.7, Vite 6, Tailwind CSS, Recharts |
| Database | PostgreSQL 16 (JSONB), Alembic migrations |
| Cache | Redis 7 |
| Testing | pytest + pytest-asyncio (backend), Vitest + RTL (frontend) |
| Linting | Ruff (backend), ESLint (frontend), Pyright (types) |
| Infrastructure | Docker Compose, GitHub Actions CI |

## Project Structure

```
agentickode/
├── backend/              # FastAPI backend
│   ├── api/              # REST routes, WebSocket, SSE, webhooks
│   │   └── servers/      # Workspace server, groups, sessions, Docker endpoints
│   ├── services/         # Business logic layer
│   │   ├── git/          # Git providers (GitHub, GitLab, Gitea, Bitbucket)
│   │   ├── adapters/     # AI agent adapters (Ollama, OpenHands, CLI)
│   │   ├── workspace/    # SSH, agent discovery, worker users, sessions
│   │   ├── notifications/# Slack, Discord, Telegram, webhooks
│   │   └── backup/       # Export/import with encryption
│   ├── worker/           # Workflow engine + step runners (bash, agent)
│   │   └── phases/       # legacy phase implementations (deprecated; see ADR-007)
│   ├── repositories/     # Database access layer
│   ├── models/           # SQLAlchemy models (16+ entities)
│   └── schemas/          # Pydantic request/response schemas
├── frontend/src/         # React/Vite frontend
│   ├── pages/            # 10 page components
│   ├── components/       # 47+ reusable components
│   │   ├── runs/         # Pipeline visualization, logs, approval
│   │   ├── servers/      # Server management UI
│   │   ├── settings/     # Configuration panels
│   │   └── shared/       # Common UI components
│   ├── api/              # API client modules
│   └── types/            # TypeScript type definitions
├── tests/                # 73 unit + 15 integration tests
├── alembic/              # 27 database migration versions
├── .github/workflows/    # CI, CLA, license check, dependency audit
└── docs/                 # Technical docs and architecture decisions
```

## Documentation

| Document | Description |
|----------|-------------|
| [`CLAUDE.md`](CLAUDE.md) | AI agent instructions and project conventions |
| [`docs/workflows.md`](docs/workflows.md) | Composable workflow reference — step kinds, triggers, templating, migration |
| [`docs/WORKER_PIPELINE.md`](docs/WORKER_PIPELINE.md) | Legacy 8-phase pipeline reference (preserved for back-compat; see `workflows.md`) |
| [`claudedocs/decisions/007-composable-step-workflows.md`](claudedocs/decisions/007-composable-step-workflows.md) | ADR-007 — design rationale for the composable model |
| [`docs/guides/09-webhook-setup.md`](docs/guides/09-webhook-setup.md) | Webhook setup for GitHub, GitLab, Gitea, Plane |
| [`claudedocs/decisions/`](claudedocs/decisions/) | Architecture decision records |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution guidelines |
| [`SECURITY.md`](SECURITY.md) | Security vulnerability reporting |

## Roadmap

- [x] Demo GIF walkthrough
- [x] Autonomous agent mode
- [x] Multi-workspace assignment with load balancing
- [x] Server groups
- [x] Persistent CLI sessions (tmux)
- [x] Docker container management
- [x] Per-server git connections
- [x] 7 CLI agent integrations with auto-install
- [ ] One-click deployment templates (Docker Hub, Railway, Coolify)
- [ ] Plugin system for custom step kinds beyond `bash` and `agent`
- [ ] Multi-tenant support with team permissions
- [ ] Built-in code review with inline commenting
- [ ] Mobile-responsive UI
- [ ] API key authentication for external integrations

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

All contributors must agree to the [Contributor License Agreement](CLA.md) before their contributions can be merged.

## Security

To report a security vulnerability, please see [SECURITY.md](SECURITY.md). Do not open a public issue.

## License

AgenticKode is dual-licensed:

- **AGPLv3** — Free for self-hosting, personal, and internal use. If you offer it as a SaaS, you must open-source your modifications. See [LICENSE](LICENSE).
- **Commercial License** — For proprietary use, SaaS offerings, or embedding without copyleft obligations. Contact info@mechemsi.com for details.

See [LICENSING.md](LICENSING.md) for full details.

---

<div align="center">

**If AgenticKode saves you time, give it a star!**

</div>

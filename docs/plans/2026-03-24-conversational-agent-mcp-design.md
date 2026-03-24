# Conversational Agent + CLI + MCP Server Design

**Date**: 2026-03-24
**Status**: Proposed

## Problem

Users interact with the platform exclusively through the web UI or raw API calls. There's no way to have a natural conversation like "fix the login bug in project X" and have the platform handle it end-to-end. OpenClaw proved that conversational agent interfaces are what users want — a single agent you chat with that controls everything.

## Solution

Three layers of programmatic access, each building on the previous:

1. **CLI tool** (`agentickode`) — Immediately usable by humans and any agent via Bash. Thin wrapper over the REST API.
2. **MCP server** — Structured tool interface for native agent integration. No text parsing needed.
3. **Built-in chat UI** — Conversational agent with persistent sessions, powered by local agents connected to the MCP server.

## CLI Tool (`agentickode`)

### Why CLI First

Every agent already has a Bash tool. A CLI gives you agent integration for free — no MCP configuration needed. It's also useful for humans, scripts, and CI/CD.

```bash
# Any agent can do this today via Bash tool:
agentickode runs create --project my-app --title "Fix login bug"
agentickode runs status 42
agentickode runs approve 42
```

### Command Structure

```bash
agentickode <resource> <action> [options]
```

#### Projects
```bash
agentickode projects list [--status active|archived]
agentickode projects get <project-id>
agentickode projects create --repo-url <url> --provider github [--name <name>] [--mode autonomous]
agentickode projects update <project-id> [--mode autonomous] [--episode-config '{"max_episodes":5}']
```

#### Runs
```bash
agentickode runs list [--project <id>] [--status running|pending|completed|failed] [--limit 20]
agentickode runs create --project <id> --title "Task title" [--description "..."] [--mode autonomous]
agentickode runs get <run-id>
agentickode runs logs <run-id> [--tail 50] [--follow]
agentickode runs cancel <run-id>
agentickode runs approve <run-id>
agentickode runs reject <run-id> [--reason "..."]
```

#### Agent Control
```bash
agentickode agent message <run-id> "Focus on auth tests first"
agentickode agent pause <run-id>
agentickode agent resume <run-id>
agentickode agent episodes <run-id>
```

#### Servers
```bash
agentickode servers list
agentickode servers add --hostname 10.0.1.50 --ssh-user root [--ssh-key-id 1]
agentickode servers setup <server-id>
agentickode servers status <server-id>
```

#### Admin
```bash
agentickode agents list
agentickode agents configure <agent-name> [--timeout 3600] [--env KEY=VALUE]
agentickode analytics [--period 7d|30d|90d]
agentickode health
```

### Implementation

**File**: `backend/cli/__init__.py` (Python package, uses `click`)

The CLI is a thin wrapper over the REST API:

```python
import click
import httpx

BASE_URL = os.environ.get("AGENTICKODE_URL", "http://localhost:8000")

@click.group()
def cli():
    """AgenticKode CLI — control your AI coding platform."""
    pass

@cli.group()
def runs():
    """Manage task runs."""
    pass

@runs.command("create")
@click.option("--project", required=True)
@click.option("--title", required=True)
@click.option("--description", default="")
@click.option("--mode", type=click.Choice(["structured", "autonomous", "hybrid"]))
def runs_create(project, title, description, mode):
    """Create a new task run."""
    resp = httpx.post(f"{BASE_URL}/api/runs", json={
        "project_id": project,
        "title": title,
        "description": description,
        **({"execution_mode": mode} if mode else {}),
    })
    run = resp.json()
    click.echo(f"Run #{run['id']} created ({run['status']})")

@runs.command("logs")
@click.argument("run_id", type=int)
@click.option("--tail", default=50)
@click.option("--follow", is_flag=True)
def runs_logs(run_id, tail, follow):
    """Show run logs, optionally following live."""
    if follow:
        # SSE streaming
        with httpx.stream("GET", f"{BASE_URL}/api/runs/{run_id}/agent-stream") as resp:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    click.echo(line[6:])
    else:
        resp = httpx.get(f"{BASE_URL}/api/runs/{run_id}/logs", params={"limit": tail})
        for log in resp.json():
            click.echo(f"[{log['phase']}] {log['message']}")
```

### Output Formats

```bash
# Default: human-readable
agentickode runs list
  #42  my-app     "Fix login bug"        running    2m ago
  #41  backend    "Add auth endpoints"   completed  1h ago

# JSON for scripting/agents
agentickode runs list --json
[{"id": 42, "project_id": "my-app", "title": "Fix login bug", ...}]

# Quiet for scripts
agentickode runs create --project my-app --title "Fix bug" --quiet
42
```

### Installation

Ships inside the Docker container. Can also be installed standalone:

```bash
pip install agentickode-cli
# or
pipx install agentickode-cli
```

### Config

```bash
# Set platform URL
export AGENTICKODE_URL=http://localhost:8000

# Or use config file
cat ~/.agentickode.yaml
url: http://localhost:8000
default_project: my-app
output: table  # table, json, quiet
```

---

## Architecture

The platform container/server hosts:

1. **FastAPI Backend** (existing)
2. **MCP Server** (NEW — FastMCP, in-process)
   - stdio transport for local agents
   - SSE transport for remote/external agents
3. **Chat Service** (NEW)
   - Session management (persistent, per-user)
   - Agent process manager (spawn/kill local processes)
   - WebSocket bridge (frontend to agent)
4. **Chat UI** (NEW) — frontend page with WebSocket connection
5. **Local agents** installed in the container: claude, opencode, gemini, aider, codex

External CLI agents can also connect over SSE without the chat UI.

## MCP Server

### Implementation

Built with **FastMCP** (Python), runs in-process with the FastAPI backend. Exposes tools organized in three tiers.

**File**: `backend/mcp/server.py`

### Tier 1 — Project and Task Management

| Tool | Description |
|------|-------------|
| `create_project` | Create a new project from a git repo URL |
| `list_projects` | List all projects with optional status filter |
| `get_project` | Get project details, config, recent runs |
| `update_project` | Update project settings |
| `create_run` | Create and queue a new task run |
| `list_runs` | List runs with filters (project, status, limit) |
| `get_run` | Get full run details with phases and episodes |
| `get_run_logs` | Get recent log entries for a run |
| `cancel_run` | Cancel a running or pending run |

### Tier 2 — Agent Control

| Tool | Description |
|------|-------------|
| `get_episodes` | List episodes for an episodic run |
| `send_message_to_agent` | Send instruction to a running agent |
| `pause_agent` | Pause a running agent |
| `resume_agent` | Resume a paused agent |
| `approve_run` | Approve a run waiting for human approval |
| `reject_run` | Reject a run with optional reason |

### Tier 3 — Administration

| Tool | Description |
|------|-------------|
| `list_servers` | List workspace servers with status |
| `add_server` | Add a new workspace server |
| `setup_server` | Run setup on a workspace server |
| `get_server_status` | Get server status with installed agents |
| `list_agents` | List all configured AI agents |
| `configure_agent` | Update agent settings |
| `get_analytics` | Platform analytics for a time period |
| `get_health` | Platform health status |

### Transport

- **stdio**: For local agents in the same container. Agent spawned as subprocess with MCP on stdin/stdout.
- **SSE**: For external agents over HTTP. Exposed at `/mcp` endpoint on FastAPI.

Each tool is a thin wrapper calling existing backend services/repositories — no new business logic needed.

## Chat Service

**File**: `backend/services/chat/chat_service.py`

### Session Lifecycle

```
create_session(user_id, agent_name)
  → spawn local agent process
  → connect MCP server via stdio
  → create DB record
  → return session handle

send_message(session_id, message)
  → write to agent stdin
  → stream response chunks from stdout
  → yield via WebSocket
  → store in history

resume_session(session_id)
  → load history from DB
  → spawn agent with --resume or inject context
  → reconnect MCP

close_session(session_id)
  → kill agent process
  → mark session closed
```

### Agent Process Management

Each session spawns a local agent process with MCP configured:

- Agent binary runs locally (no SSH)
- stdin/stdout piped for communication
- MCP config points agent to platform's tools
- Process managed by asyncio (create_subprocess)

### MCP Config for Local Agent

```json
{
  "mcpServers": {
    "agentickode": {
      "command": "python",
      "args": ["-m", "backend.mcp.server"],
      "env": {
        "DATABASE_URL": "...",
        "PLATFORM_URL": "http://localhost:8000"
      }
    }
  }
}
```

### Session Persistence Model

```
ChatSession:
  id: UUID
  user_id: str
  agent_name: str (claude, opencode, gemini, etc.)
  display_name: str (user-set session name)
  status: str (active, idle, closed)
  messages: JSONB (conversation history)
  agent_session_id: str (for --resume support)
  created_at: datetime
  last_activity_at: datetime
```

## Chat UI

### Frontend Pages and Components

- `Chat.tsx` — Full-page chat interface
- `ChatSidebar.tsx` — Session list with new/resume/delete
- `ChatThread.tsx` — Message thread with streaming
- `ToolCallCard.tsx` — Collapsible tool call rendering
- `AgentSelector.tsx` — Pick which agent to chat with

### WebSocket Protocol

```
Client → Server:  {"type": "message", "content": "Fix the login bug"}
Server → Client:  {"type": "chunk", "content": "I'll look into..."}
Server → Client:  {"type": "tool_call", "tool": "get_project", "args": {...}}
Server → Client:  {"type": "tool_result", "result": {...}}
Server → Client:  {"type": "chunk", "content": "Created run #42..."}
Server → Client:  {"type": "done"}
```

### Agent System Prompt

Each session includes a system prompt:

```
You are the AI manager for AgenticKode, a coding automation platform.

You can control the platform through the available MCP tools:
- Create and manage projects (create_project, list_projects, etc.)
- Create and monitor task runs (create_run, get_run, etc.)
- Control running agents (send_message_to_agent, pause, resume)
- Manage workspace servers (list_servers, setup_server, etc.)
- View analytics and health (get_analytics, get_health)

When the user asks you to do something with code:
1. Identify which project they're referring to
2. Create a task run with a clear description
3. Monitor progress and report back

Be conversational and proactive. If a run fails, investigate why.
```

## External Agent Support

Any MCP-compatible CLI agent can connect without the chat UI:

### Claude Code

Add to settings:
```json
{
  "mcpServers": {
    "agentickode": {
      "type": "sse",
      "url": "http://platform-host:8000/mcp"
    }
  }
}
```

Then use normally — Claude can call all platform tools.

### Other Agents

Any agent supporting MCP SSE transport can connect to the same endpoint.

## Implementation Phases

### Phase 1: CLI Tool (immediate agent access)
- `backend/cli/__init__.py` — Click CLI app
- `backend/cli/projects.py` — Project commands
- `backend/cli/runs.py` — Run commands (create, list, get, logs, approve, cancel)
- `backend/cli/agent.py` — Agent control commands (message, pause, resume, episodes)
- `backend/cli/servers.py` — Server commands
- `backend/cli/admin.py` — Admin commands (agents, analytics, health)
- `backend/cli/output.py` — Output formatters (table, json, quiet)
- `pyproject.toml` entry point: `agentickode = "backend.cli:cli"`
- Tests for each command group

### Phase 2: MCP Server (structured tools)
- `backend/mcp/__init__.py`
- `backend/mcp/server.py` — FastMCP server setup
- `backend/mcp/tools/projects.py` — Tier 1 tools
- `backend/mcp/tools/agent_control.py` — Tier 2 tools
- `backend/mcp/tools/admin.py` — Tier 3 tools
- SSE transport endpoint on FastAPI
- Tests for each tool

### Phase 3: Chat Service (core)
- `backend/services/chat/chat_service.py` — Session management
- `backend/services/chat/agent_process.py` — Local process spawning
- `backend/models/chat.py` — ChatSession model + migration
- `backend/api/chat.py` — WebSocket endpoint
- Tests

### Phase 4: Chat UI (frontend)
- `frontend/src/pages/Chat.tsx` — Main chat page
- `frontend/src/components/chat/` — Sidebar, thread, tool cards, agent selector
- Route and navigation

### Phase 5: Session Persistence and Polish
- Conversation history in DB
- Resume sessions with context
- Agent switching mid-session
- Session naming and organization

## File Structure

```
backend/
  cli/                         # Phase 1: CLI tool
    __init__.py                # Click app entry point
    projects.py                # project commands
    runs.py                    # run commands
    agent.py                   # agent control commands
    servers.py                 # server commands
    admin.py                   # admin commands
    output.py                  # table/json/quiet formatters
  mcp/                         # Phase 2: MCP server
    __init__.py
    server.py                  # FastMCP server setup
    tools/
      __init__.py
      projects.py              # Tier 1 tools
      agent_control.py         # Tier 2 tools
      admin.py                 # Tier 3 tools
  services/
    chat/                      # Phase 3: Chat service
      __init__.py
      chat_service.py          # Session lifecycle
      agent_process.py         # Local agent spawning
  models/
    chat.py                    # ChatSession model
  api/
    chat.py                    # WebSocket + REST

frontend/src/                  # Phase 4: Chat UI
  pages/
    Chat.tsx
  components/
    chat/
      ChatSidebar.tsx
      ChatThread.tsx
      ToolCallCard.tsx
      AgentSelector.tsx
```

## Example Interactions

### Via CLI (any agent using Bash tool)
```
Agent thinks: "I need to fix failing tests in backend-api"
Agent runs:   agentickode runs create --project backend-api --title "Fix failing tests"
Output:       Run #47 created (pending)
Agent runs:   agentickode runs logs 47 --follow
Output:       [agent_loop] Starting episode 1/5...
              [agent_loop] Episode 1 done: completed=true, turns=24
Agent runs:   agentickode runs get 47
Output:       Run #47  backend-api  "Fix failing tests"  completed  PR #123
```

### Via Chat UI (MCP tools)

#### Simple task
```
User: "Fix the failing tests in project backend-api"
Agent: [calls get_project("backend-api")] Got it — backend-api on GitHub.
       [calls create_run(project_id="backend-api", title="Fix failing tests",
              description="Run test suite, identify failures, fix them")]
       Created run #47. I'll monitor it.
       ...
       [calls get_run(47)] Run #47 completed. PR #123 created with 3 test fixes.
       Want me to approve it?
```

### Multi-project orchestration
```
User: "Run tests on all active projects"
Agent: [calls list_projects()] Found 5 active projects.
       [calls create_run() x5] Created runs #48-52.
       Monitoring... 3/5 done. #50 failed — authentication timeout.
       Want me to investigate #50?
```

### Server management
```
User: "Add my new dev server at 10.0.1.50"
Agent: [calls add_server(hostname="10.0.1.50", ssh_user="root")]
       Server added. Running setup...
       [calls setup_server(server_id=4)]
       Setup complete. Claude CLI and Codex installed. Ready for tasks.
```

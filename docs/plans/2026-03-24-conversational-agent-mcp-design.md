# Conversational Agent + MCP Server Design

**Date**: 2026-03-24
**Status**: Proposed

## Problem

Users interact with the platform exclusively through the web UI or raw API calls. There's no way to have a natural conversation like "fix the login bug in project X" and have the platform handle it end-to-end. OpenClaw proved that conversational agent interfaces are what users want — a single agent you chat with that controls everything.

## Solution

Add a **conversational AI manager** to the platform — a local agent (Claude, OpenCode, Gemini) that users chat with through a built-in chat UI or any external CLI tool. The agent connects to the platform via an **MCP server** that exposes all platform operations as tools.

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

### Phase 1: MCP Server (foundation)
- `backend/mcp/__init__.py`
- `backend/mcp/server.py` — FastMCP server setup
- `backend/mcp/tools/projects.py` — Tier 1 tools
- `backend/mcp/tools/agent_control.py` — Tier 2 tools
- `backend/mcp/tools/admin.py` — Tier 3 tools
- SSE transport endpoint on FastAPI
- Tests for each tool

### Phase 2: Chat Service (core)
- `backend/services/chat/chat_service.py` — Session management
- `backend/services/chat/agent_process.py` — Local process spawning
- `backend/models/chat.py` — ChatSession model + migration
- `backend/api/chat.py` — WebSocket endpoint
- Tests

### Phase 3: Chat UI (frontend)
- `frontend/src/pages/Chat.tsx` — Main chat page
- `frontend/src/components/chat/` — Sidebar, thread, tool cards, agent selector
- Route and navigation

### Phase 4: Session Persistence and Polish
- Conversation history in DB
- Resume sessions with context
- Agent switching mid-session
- Session naming and organization

## File Structure

```
backend/
  mcp/
    __init__.py
    server.py
    tools/
      __init__.py
      projects.py
      agent_control.py
      admin.py
  services/
    chat/
      __init__.py
      chat_service.py
      agent_process.py
  models/
    chat.py
  api/
    chat.py

frontend/src/
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

### Simple task
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

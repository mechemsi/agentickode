<!-- Copyright (c) 2026 Mechemsi. All rights reserved. -->
<!-- Licensed under AGPLv3. See LICENSE file. -->
<!-- Commercial licensing: info@mechemsi.com -->

# Persistent CLI Sessions — Design Document

## Summary

Add persistent, attach/detach CLI sessions for Claude and Codex on workspace servers.
Sessions survive browser disconnects via tmux on remote servers. Users can start
standalone sessions from the server page or keep task-linked sessions alive after
pipeline phases complete. A hybrid UI offers both terminal and chat views.

## Data Model

### CliSession table

```sql
CREATE TABLE cli_sessions (
    id              SERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL UNIQUE,        -- UUID, used as --session-id for Claude or tmux name
    workspace_server_id INT NOT NULL REFERENCES workspace_servers(id) ON DELETE CASCADE,
    project_id      TEXT REFERENCES project_configs(project_id) ON DELETE SET NULL,
    task_run_id     INT REFERENCES task_runs(id) ON DELETE SET NULL,
    agent_name      TEXT NOT NULL,               -- "claude", "codex"
    user_context    TEXT NOT NULL DEFAULT 'coder',-- OS user running the session
    workspace_path  TEXT,                        -- working directory
    display_name    TEXT,                        -- user-given or auto-generated
    tmux_session    TEXT NOT NULL,               -- tmux session name
    pid             INT,                         -- agent process PID inside tmux
    status          TEXT NOT NULL DEFAULT 'starting',
    remote_control_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    remote_control_port INT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at       TIMESTAMPTZ,
    metadata_       JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Status state machine

```
starting → active ⇄ idle → closed
                ↓         ↗
            detached → closed
                ↓
            active (re-attached)

Any state → error (crash/tmux died)
Any state → closed (explicit end)
```

## Backend Services

### SessionService (`backend/services/workspace/session_service.py`)

Core methods:

- `create_session(server, agent_name, user_context, project_id?, workspace_path?, task_run_id?)`
  - Generate UUID session_id
  - SSH: `tmux new-session -d -s "{tmux_name}" -x 200 -y 50`
  - For Claude: send `claude --session-id {session_id} --dangerously-skip-permissions` then `/remote-control enable`
  - For Codex: send `codex` into tmux
  - If project selected: cd to project workspace first
  - Insert CliSession with status="starting", poll to confirm → "active"

- `attach_session(session)` → returns tmux session name for terminal WS to attach
  - Update status → "active", last_activity_at

- `detach_session(session)`
  - Update status → "detached"

- `close_session(session)`
  - SSH: `tmux kill-session -t {tmux_name}`
  - Claude: cleanup lock/pid files
  - Update status → "closed", closed_at

- `send_command(session, message)` → str
  - SSH: `tmux send-keys -t {tmux_name} "{escaped_message}" Enter`
  - Sleep briefly, then capture output

- `capture_output(session, lines=50)` → str
  - SSH: `tmux capture-pane -t {tmux_name} -p -S -{lines}`

- `check_health(server_id)` → list of session statuses
  - SSH: `tmux list-sessions -F "#{session_name} #{session_activity}"`
  - Compare with DB records, update statuses

- `list_server_sessions(server_id)` → list of tmux sessions on server

### API Endpoints (`backend/api/servers/sessions.py`)

```
POST   /api/sessions                         — Create session (body: server_id, agent_name, user_context, project_id?, name?)
GET    /api/sessions                         — List sessions (query: server_id?, project_id?, status?, agent_name?)
GET    /api/sessions/{id}                    — Get session detail
DELETE /api/sessions/{id}                    — Close/kill session
POST   /api/sessions/{id}/send              — Send command (body: message) — Claude remote-control
GET    /api/sessions/{id}/capture            — Capture tmux pane content (query: lines=50)
GET    /api/workspace-servers/{sid}/sessions — List sessions on server (convenience)
WS     /ws/sessions/{session_id}/terminal   — Attach terminal to session via tmux
```

### Schemas (`backend/schemas/sessions.py`)

```python
class CliSessionCreate(BaseModel):
    workspace_server_id: int
    agent_name: str          # "claude" | "codex"
    user_context: str = "coder"
    project_id: str | None = None
    workspace_path: str | None = None
    display_name: str | None = None

class CliSessionOut(BaseModel):
    id: int
    session_id: str
    workspace_server_id: int
    project_id: str | None
    task_run_id: int | None
    agent_name: str
    user_context: str
    workspace_path: str | None
    display_name: str | None
    tmux_session: str
    status: str
    remote_control_enabled: bool
    started_at: datetime
    last_activity_at: datetime
    closed_at: datetime | None

class SessionSendRequest(BaseModel):
    message: str

class SessionCaptureResponse(BaseModel):
    output: str
    lines: int
```

### WebSocket Terminal Attach (`backend/api/ws.py`)

New endpoint: `/ws/sessions/{session_id}/terminal`

```python
@router.websocket("/ws/sessions/{session_id}/terminal")
async def ws_session_terminal(websocket, session_id):
    # 1. Load CliSession from DB by session_id
    # 2. Verify status is not "closed"
    # 3. Load WorkspaceServer
    # 4. SSH to server
    # 5. Attach: tmux attach-session -t {tmux_session}
    # 6. Bridge PTY ↔ WebSocket
    # 7. Update status → "active" on connect
    # 8. Update status → "detached" on disconnect
    # 9. Update last_activity_at periodically
```

### WorkerEngine Health Check

Add to `_tick()` — every 30s check session health:

```python
async def _check_sessions(self):
    # Group active sessions by server
    # One SSH per server: tmux list-sessions
    # Compare with DB, update stale entries
    # Mark closed/error for sessions whose tmux died
```

### Coding Phase Integration

In `backend/worker/phases/coding.py`, after phase completes:

```python
if session_id and project_config.keep_session_alive:
    # Create CliSession record with task_run_id, status="idle"
    # DON'T call close_cli_session()
else:
    await close_cli_session(...)  # current behavior
```

## Frontend

### SessionsPanel (`frontend/src/components/servers/SessionsPanel.tsx`)

Expandable panel on each server card showing:
- List of active/idle/detached sessions
- Status dot (green=active, yellow=idle/detached)
- Agent icon, short ID, project name, user, last activity
- Actions: Attach Terminal, Chat (Claude only), End Session
- "+ New Claude Session" / "+ New Codex Session" buttons
- Inline form for new session: user picker, optional project, optional name

### ChatPanel (`frontend/src/components/servers/ChatPanel.tsx`)

Claude-only structured command interface:
- Message input + Send button
- Captures tmux output after sending, displays as chat bubbles
- Uses POST /api/sessions/{id}/send and GET /api/sessions/{id}/capture
- Lightweight — real session runs in tmux, this pipes text in/out

### Server Card Badge

In WorkspaceServers.tsx, each server shows:
```
5 agents · 5 projects · 2 active sessions
```

Session count fetched from GET /api/workspace-servers/{id}/sessions.

### Sessions Button

New "Sessions" button in server toolbar, same pattern as Docker/Terminal:
```tsx
<button onClick={() => toggleSet(setSessionsExpanded, s.id)}>
  <Monitor /> Sessions {sessionCounts[s.id] ? `(${sessionCounts[s.id]})` : ""}
</button>
```

### Run Detail Integration

On RunDetail.tsx, if run has a linked CliSession that's still alive:
```tsx
{linkedSession && linkedSession.status !== "closed" && (
  <div>
    <span>Active Session: {linkedSession.display_name}</span>
    <button onClick={attachToSession}>Attach</button>
    <button onClick={endSession}>End</button>
  </div>
)}
```

### Types (`frontend/src/types/sessions.ts`)

```typescript
interface CliSession {
  id: number;
  session_id: string;
  workspace_server_id: number;
  project_id: string | null;
  task_run_id: number | null;
  agent_name: string;
  user_context: string;
  workspace_path: string | null;
  display_name: string | null;
  tmux_session: string;
  status: "starting" | "active" | "idle" | "detached" | "closed" | "error";
  remote_control_enabled: boolean;
  started_at: string;
  last_activity_at: string;
  closed_at: string | null;
}
```

### API Client (`frontend/src/api/sessions.ts`)

Functions for all session endpoints: create, list, get, close, send, capture, listByServer.

## Implementation Order

| Step | What | Files | Depends On |
|------|------|-------|------------|
| 1 | CliSession model + migration | model, migration | — |
| 2 | SessionService (tmux mgmt) | service | Step 1 |
| 3 | Sessions API + schemas | api, schemas | Steps 1-2 |
| 4 | Session terminal WebSocket | ws.py | Steps 1-3 |
| 5 | Health check in engine | engine.py | Steps 1-2 |
| 6 | Frontend types + API client | types, api | Step 3 |
| 7 | SessionsPanel component | component | Step 6 |
| 8 | ChatPanel component | component | Step 6 |
| 9 | Server card badges + button | WorkspaceServers.tsx | Steps 6-7 |
| 10 | Run detail integration | RunDetail.tsx | Steps 6-7 |
| 11 | Coding phase keep-alive | coding.py | Steps 1-2 |

Steps 1-5 (backend) can be parallelized into 2-3 agents.
Steps 6-10 (frontend) can be parallelized into 2-3 agents.
Step 11 is a small follow-up.

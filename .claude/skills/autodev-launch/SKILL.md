---
name: autodev-launch
description: Launch an AI agent (Claude, Codex, etc.) on a project's workspace server. Checks workspace readiness, handles multi-workspace selection, and creates an interactive session. Triggers on /autodev-launch or "launch claude on", "start agent on", "open session on project".
---

# Launch Agent on Workspace

Launch an AI agent on a project's workspace server with automatic readiness checking.

**API Base:** `http://localhost:8000/api`

## Usage

**`/autodev-launch`** — Interactive: list projects, pick one, check workspaces, launch
**`/autodev-launch <project-slug>`** — Launch on specific project
**`/autodev-launch <project-slug> <agent>`** — Launch specific agent (default: claude)

## Workflow

### Step 1: Resolve Project

If no project specified, list and ask:

```bash
curl -s http://localhost:8000/api/projects | python3 -c "
import json, sys
for p in json.load(sys.stdin):
    ws = len(p.get('workspace_server_ids', []))
    if ws > 0:
        print(f\"  {p['project_slug']:30s} {p['repo_owner']}/{p['repo_name']}  ({ws} workspace{'s' if ws != 1 else ''})\")"
```

Only show projects that have workspace servers assigned.

### Step 2: Check Workspace Readiness

```bash
curl -s http://localhost:8000/api/projects/<PROJECT_ID>/workspace-readiness | python3 -c "
import json, sys
data = json.load(sys.stdin)
for w in data['workspaces']:
    icon = '✓' if w['status'] == 'ready' else '✗'
    print(f\"  {icon} {w['server_name']:20s} {w['status']:12s} {w.get('path', '')}\")"
```

### Step 3: Select Workspace

- **One ready workspace** → auto-select, proceed
- **Multiple ready** → ask user to pick by server name
- **None ready** → report which are `not_cloned` or `unreachable`, ask if user wants to create a run first (which will clone the repo via workspace_setup phase)

### Step 4: Create Session

```bash
curl -s -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_server_id": <SERVER_ID>,
    "agent_name": "<AGENT>",
    "project_id": "<PROJECT_ID>",
    "workspace_path": "<PATH>",
    "user_context": "root",
    "display_name": "<AGENT> @ <PROJECT_SLUG>"
  }'
```

Use the `path` from the readiness check as `workspace_path`.
Default agent is `claude`. Default user_context is `root`.

### Step 5: Report Session

Extract session details and report to user:

```bash
curl -s http://localhost:8000/api/sessions/<SESSION_ID> | python3 -c "
import json, sys
s = json.load(sys.stdin)
print(f'Session created:')
print(f'  ID:     {s[\"id\"]}')
print(f'  UUID:   {s[\"session_id\"]}')
print(f'  Agent:  {s[\"agent_name\"]}')
print(f'  Server: {s.get(\"server_name\", \"unknown\")}')
print(f'  Status: {s[\"status\"]}')
print(f'  Tmux:   {s[\"tmux_session\"]}')
print(f'  Path:   {s.get(\"workspace_path\", \"\")}')
"
```

Tell the user:
- The session is active and the agent is running
- They can interact via the UI terminal (WorkspaceServers page → Sessions tab)
- Or use `/autodev-session send <session-id> <message>` to send commands

## Notes

- Agent names: claude, codex, gemini, aider, opencode
- Sessions persist until explicitly closed
- The session attaches via tmux on the remote workspace server

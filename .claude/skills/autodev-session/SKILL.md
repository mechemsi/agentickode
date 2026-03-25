---
name: autodev-session
description: Use when the user wants to interact with a running agent session on a workspace server — sending commands, reading output, listing active sessions, or closing them. Use this for "send this to the agent", "what's the agent doing", "check session output", "close that session", "list my sessions", or any tmux-based agent interaction.
---

# Session Management

Manage persistent AI agent sessions on workspace servers.

**API Base:** `http://localhost:8000/api`

## Usage

**`/autodev-session`** — List active sessions
**`/autodev-session list`** — List all active sessions
**`/autodev-session send <id> <message>`** — Send a command to a session
**`/autodev-session capture <id>`** — Capture current output from a session
**`/autodev-session close <id>`** — Close a session
**`/autodev-session create <server-id> <agent>`** — Create a new session manually

## Commands

### List Sessions

```bash
curl -s http://localhost:8000/api/sessions | python3 -c "
import json, sys
sessions = json.load(sys.stdin)
if not sessions:
    print('No active sessions.')
else:
    print(f'{\"ID\":>4s}  {\"Agent\":10s}  {\"Server\":15s}  {\"Status\":10s}  {\"Project\":20s}  {\"Path\"}')
    print('-' * 80)
    for s in sessions:
        print(f'{s[\"id\"]:4d}  {s[\"agent_name\"]:10s}  {(s.get(\"server_name\") or \"-\"):15s}  {s[\"status\"]:10s}  {(s.get(\"project_id\") or \"-\"):20s}  {s.get(\"workspace_path\",\"\")[:30]}')
"
```

### Send to Session

Send a message/command and capture the response:

```bash
curl -s -X POST http://localhost:8000/api/sessions/<SESSION_ID>/send \
  -H "Content-Type: application/json" \
  -d '{"message": "<MESSAGE>"}' | python3 -c "
import json, sys
r = json.load(sys.stdin)
print(r.get('output', 'No output captured'))
"
```

### Capture Output

Read current terminal output without sending anything:

```bash
curl -s "http://localhost:8000/api/sessions/<SESSION_ID>/capture?lines=80" | python3 -c "
import json, sys
r = json.load(sys.stdin)
print(r.get('output', 'No output'))
"
```

### Close Session

```bash
curl -s -X DELETE http://localhost:8000/api/sessions/<SESSION_ID> | python3 -c "
import json, sys
print(json.load(sys.stdin).get('detail', 'Done'))
"
```

### Create Session

```bash
curl -s -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_server_id": <SERVER_ID>,
    "agent_name": "<AGENT>",
    "user_context": "root"
  }' | python3 -c "
import json, sys
s = json.load(sys.stdin)
print(f'Session #{s[\"id\"]} created: {s[\"agent_name\"]} on {s.get(\"server_name\", \"server\")} (tmux: {s[\"tmux_session\"]})')
"
```

## Interactive Workflow

When the user says "send X to session Y":
1. Send the message
2. Wait 3-5 seconds
3. Capture and display the output
4. Ask if they want to send more

When polling a long-running agent task:
1. Capture output every 15-20 seconds
2. Show new output only (diff from last capture)
3. Stop when agent appears idle or user says stop

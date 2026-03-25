---
name: autodev-server
description: Manage workspace servers — list, test connectivity, check health, view agents, and setup servers. Triggers on /autodev-server or "list servers", "check server", "server status", "add server", "setup server".
---

# Server Administration

Manage workspace servers on the AgenticKode platform.

**API Base:** `http://localhost:8000/api`

## Usage

**`/autodev-server`** — List all workspace servers with status
**`/autodev-server list`** — Same as above
**`/autodev-server <id>`** — Show server detail with agents
**`/autodev-server test <id>`** — Test SSH connectivity
**`/autodev-server health`** — Platform health check
**`/autodev-server agents <id>`** — List agents on a server

## Commands

### List Servers

```bash
curl -s http://localhost:8000/api/workspace-servers | python3 -c "
import json, sys
servers = json.load(sys.stdin)
if not servers:
    print('No workspace servers configured.')
else:
    print(f'{\"ID\":>3s}  {\"Name\":20s}  {\"Host\":25s}  {\"Status\":10s}  {\"Agents\":>6s}  {\"Projects\":>8s}')
    print('-' * 80)
    for s in servers:
        print(f'{s[\"id\"]:3d}  {s[\"name\"]:20s}  {s[\"hostname\"]:25s}  {s.get(\"status\",\"-\"):10s}  {s.get(\"agent_count\",0):6d}  {s.get(\"project_count\",0):8d}')
"
```

### Server Detail

```bash
curl -s http://localhost:8000/api/workspace-servers/<SERVER_ID> | python3 -c "
import json, sys
s = json.load(sys.stdin)
print(f'Server: {s[\"name\"]} (#{s[\"id\"]})')
print(f'  Host:     {s[\"hostname\"]}:{s.get(\"port\", 22)}')
print(f'  User:     {s.get(\"username\", \"root\")}')
print(f'  Root:     {s.get(\"workspace_root\", \"/workspaces\")}')
print(f'  Status:   {s.get(\"status\", \"unknown\")}')
print(f'  Worker:   {s.get(\"worker_user\", \"-\")} ({s.get(\"worker_user_status\", \"-\")})')
print(f'  Max jobs: {s.get(\"max_concurrent_tasks\", 1)}')
if s.get('agents'):
    print(f'  Agents:')
    for a in s['agents']:
        avail = 'available' if a.get('available') else 'unavailable'
        print(f'    - {a[\"agent_name\"]:12s} ({a.get(\"user_context\",\"admin\"):8s}) {avail}  {a.get(\"version\",\"\")}')
"
```

### Test Connectivity

```bash
curl -s -X POST http://localhost:8000/api/workspace-servers/<SERVER_ID>/test | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('success'):
    print(f'SSH connection successful')
    if r.get('os_info'): print(f'  OS: {r[\"os_info\"]}')
else:
    print(f'SSH connection failed: {r.get(\"error\", \"unknown\")}')
"
```

### Platform Health

```bash
curl -s http://localhost:8000/api/health | python3 -c "
import json, sys
h = json.load(sys.stdin)
print(f'Platform Health: {h.get(\"status\", \"unknown\")}')
for k, v in h.items():
    if k != 'status':
        if isinstance(v, dict):
            print(f'  {k}:')
            for sk, sv in v.items():
                print(f'    {sk}: {sv}')
        else:
            print(f'  {k}: {v}')
"
```

### List Server Sessions

```bash
curl -s http://localhost:8000/api/workspace-servers/<SERVER_ID>/sessions | python3 -c "
import json, sys
sessions = json.load(sys.stdin)
for s in sessions:
    print(f'  #{s[\"id\"]}  {s[\"agent_name\"]:10s}  {s[\"status\"]:10s}  {s.get(\"display_name\",\"\")}')
"
```

## Notes

- Server status values: unknown, ready, degraded
- Worker user setup is automatic during server setup
- Use `/autodev-launch` to launch agents on servers (handles readiness checks)

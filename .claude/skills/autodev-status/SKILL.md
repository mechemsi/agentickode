---
name: autodev-status
description: Check platform status — list runs, see running/pending/failed tasks, system health, and analytics. Triggers on /autodev-status or "what's running", "check status", "show runs", "platform health".
---

# Platform Status

Check the status of runs, system health, and analytics on the AgenticKode platform.

**API Base:** `http://localhost:8000/api`

## Usage

**`/autodev-status`** — Overview: active runs + health summary
**`/autodev-status runs`** — List recent runs with status
**`/autodev-status <run-id>`** — Detail for a specific run
**`/autodev-status health`** — System health check
**`/autodev-status analytics`** — Run analytics summary

## Commands

### Overview (default)

Show active runs and quick health:

```bash
curl -s http://localhost:8000/api/runs | python3 -c "
import json, sys
runs = json.load(sys.stdin)
active = [r for r in runs if r['status'] in ('pending', 'running', 'awaiting_approval')]
recent = sorted(runs, key=lambda r: r.get('updated_at', ''), reverse=True)[:10]
print('=== Active Runs ===')
if not active:
    print('  No active runs.')
for r in active:
    print(f'  #{r[\"id\"]:4d}  {r[\"status\"]:20s}  {r.get(\"current_phase\",\"-\"):18s}  {r.get(\"title\",\"\")[:50]}')
print()
print('=== Recent Runs (last 10) ===')
for r in recent:
    print(f'  #{r[\"id\"]:4d}  {r[\"status\"]:20s}  {r.get(\"title\",\"\")[:60]}')
"
```

Then check health:

```bash
curl -s http://localhost:8000/api/health | python3 -c "
import json, sys
h = json.load(sys.stdin)
print(f'Health: {h.get(\"status\", \"unknown\")}')
for k, v in h.items():
    if k != 'status':
        print(f'  {k}: {v}')
"
```

### Run Detail

```bash
curl -s http://localhost:8000/api/runs/<RUN_ID> | python3 -c "
import json, sys
r = json.load(sys.stdin)
print(f'Run #{r[\"id\"]}')
print(f'  Title:   {r.get(\"title\", \"\")}')
print(f'  Project: {r.get(\"project_id\", \"\")}')
print(f'  Status:  {r[\"status\"]}')
print(f'  Phase:   {r.get(\"current_phase\", \"-\")}')
print(f'  Branch:  {r.get(\"branch_name\", \"-\")}')
print(f'  PR:      {r.get(\"pr_url\", \"-\")}')
if r.get('error_message'):
    print(f'  Error:   {r[\"error_message\"][:200]}')
print(f'  Created: {r.get(\"created_at\", \"\")}')
print(f'  Updated: {r.get(\"updated_at\", \"\")}')
"
```

### Analytics

```bash
curl -s http://localhost:8000/api/analytics/summary | python3 -c "
import json, sys
a = json.load(sys.stdin)
print('=== Analytics ===')
for k, v in a.items():
    print(f'  {k}: {v}')
"
```

## Presentation

- Use tables/formatting to make the output scannable
- Highlight any failed or stuck runs
- For awaiting_approval runs, remind user they can approve via `/autodev-run`
- Show time since last activity for active runs

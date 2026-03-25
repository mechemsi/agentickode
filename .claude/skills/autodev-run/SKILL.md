---
name: autodev-run
description: Use when the user wants to dispatch a coding task to a remote workspace — fixing bugs, implementing features, running the 8-phase pipeline, or creating a PR automatically. Use this even if the user just says "fix the login bug on myproject" or "run this task" or "create a run" or "implement X on Y". Also use when the user asks to approve or reject a pending run.
---

# Create & Monitor Run

Create a coding task run on the AgenticKode platform and monitor it to completion.

**API Base:** `http://localhost:8000/api`

## Usage

**`/autodev-run <task-description>`** — Interactive: list projects, let user pick, create run
**`/autodev-run <project-slug> <task-description>`** — Direct: create run on specific project

## Workflow

### Step 1: Resolve Project

If no project specified, list available projects and ask user to pick:

```bash
curl -s http://localhost:8000/api/projects | python3 -c "
import json, sys
projects = json.load(sys.stdin)
for p in projects:
    ws = len(p.get('workspace_server_ids', []))
    print(f\"  {p['project_slug']:30s} {p['repo_owner']}/{p['repo_name']}  ({ws} workspace{'s' if ws != 1 else ''})\")"
```

Ask user to pick a project by slug name.

### Step 2: Create the Run

```bash
curl -s -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "<PROJECT_ID>",
    "title": "<TASK_DESCRIPTION>",
    "description": "<EXPANDED_DESCRIPTION>"
  }' | python3 -c "import json,sys; r=json.load(sys.stdin); print(f'Run #{r[\"id\"]} created — status: {r[\"status\"]}')"
```

Replace `<PROJECT_ID>` with the project's `project_id`, and fill in the title/description from the user's task.

### Step 3: Monitor Progress

Poll every 15 seconds until the run reaches a terminal state (`completed`, `failed`, `cancelled`) or `awaiting_approval`:

```bash
curl -s http://localhost:8000/api/runs/<RUN_ID> | python3 -c "
import json, sys
r = json.load(sys.stdin)
phase = r.get('current_phase', 'unknown')
status = r['status']
print(f'Run #{r[\"id\"]}: {status} (phase: {phase})')
if r.get('error_message'):
    print(f'  Error: {r[\"error_message\"][:200]}')
"
```

Report each phase transition to the user. Terminal states:
- **completed** — Report success, show PR link if available
- **failed** — Report error message and which phase failed
- **awaiting_approval** — Tell user a PR is ready for review, offer to approve/reject

### Step 4: Handle Approval (if needed)

If the run reaches `awaiting_approval`:

**Approve:**
```bash
curl -s -X POST http://localhost:8000/api/runs/<RUN_ID>/approve \
  -H "Content-Type: application/json" \
  -d '{"merge": true}'
```

**Reject:**
```bash
curl -s -X POST http://localhost:8000/api/runs/<RUN_ID>/reject \
  -H "Content-Type: application/json" \
  -d '{"reason": "<REASON>"}'
```

### Step 5: Get Results

Once completed, fetch the final run details including logs:

```bash
curl -s http://localhost:8000/api/runs/<RUN_ID>/logs | python3 -c "
import json, sys
logs = json.load(sys.stdin)
for entry in logs[-20:]:
    print(f'[{entry.get(\"phase\",\"\")}] {entry.get(\"message\",\"\")[:150]}')
"
```

## Notes

- Polling interval: 15 seconds for active runs
- Report each phase change to the user as it happens
- If a run takes more than 10 minutes, ask the user if they want to keep waiting
- The 8 phases are: workspace_setup, init, planning, coding, testing, reviewing, approval, finalization

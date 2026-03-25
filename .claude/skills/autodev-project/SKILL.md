---
name: autodev-project
description: Manage projects — list, create, update, and check workspace readiness. Triggers on /autodev-project or "list projects", "add project", "create project", "project settings".
---

# Project Management

Manage projects on the AgenticKode platform.

**API Base:** `http://localhost:8000/api`

## Usage

**`/autodev-project`** — List all projects
**`/autodev-project list`** — Same as above
**`/autodev-project <slug>`** — Show project detail
**`/autodev-project create`** — Interactive project creation
**`/autodev-project readiness <slug>`** — Check workspace readiness

## Commands

### List Projects

```bash
curl -s http://localhost:8000/api/projects | python3 -c "
import json, sys
projects = json.load(sys.stdin)
if not projects:
    print('No projects configured.')
else:
    print(f'{\"Slug\":25s}  {\"Repo\":35s}  {\"Provider\":8s}  {\"Source\":8s}  {\"Workspaces\":>10s}')
    print('-' * 95)
    for p in projects:
        repo = f'{p[\"repo_owner\"]}/{p[\"repo_name\"]}'
        ws = len(p.get('workspace_server_ids', []))
        print(f'{p[\"project_slug\"]:25s}  {repo:35s}  {p[\"git_provider\"]:8s}  {p[\"task_source\"]:8s}  {ws:10d}')
"
```

### Project Detail

Find by slug, then fetch by project_id:

```bash
curl -s http://localhost:8000/api/projects | python3 -c "
import json, sys
projects = json.load(sys.stdin)
slug = '<SLUG>'
match = [p for p in projects if p['project_slug'] == slug]
if not match:
    print(f'Project \"{slug}\" not found')
    sys.exit(1)
p = match[0]
print(f'Project: {p[\"project_slug\"]}')
print(f'  ID:       {p[\"project_id\"]}')
print(f'  Repo:     {p[\"repo_owner\"]}/{p[\"repo_name\"]}')
print(f'  Branch:   {p[\"default_branch\"]}')
print(f'  Provider: {p[\"git_provider\"]}')
print(f'  Source:   {p[\"task_source\"]}')
print(f'  Path:     {p.get(\"workspace_path\", \"-\")}')
print(f'  Servers:  {p.get(\"workspace_server_ids\", [])}')
print(f'  Token:    {\"configured\" if p.get(\"has_git_provider_token\") else \"not set\"}')
auto = p.get('autonomy_config') or {}
print(f'  Mode:     {auto.get(\"execution_mode\", \"structured\")}')
"
```

### Check Workspace Readiness

```bash
curl -s http://localhost:8000/api/projects/<PROJECT_ID>/workspace-readiness | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'Workspace readiness for {data[\"project_id\"]}:')
for w in data['workspaces']:
    icon = 'OK' if w['status'] == 'ready' else 'NO'
    print(f'  [{icon}] {w[\"server_name\"]:20s}  {w[\"status\"]:12s}  {w.get(\"path\",\"\")}')
    if w.get('error'):
        print(f'       Error: {w[\"error\"]}')
"
```

### Create Project

Ask the user for:
1. Git URL (e.g., `git@github.com:owner/repo.git` or HTTPS URL)
2. Which workspace server(s) to assign

Then parse the URL first:

```bash
curl -s -X POST http://localhost:8000/api/projects/parse-git-url \
  -H "Content-Type: application/json" \
  -d '{"git_url": "<GIT_URL>"}' | python3 -c "
import json, sys
r = json.load(sys.stdin)
print(f'Detected: {r[\"provider\"]} — {r[\"owner\"]}/{r[\"repo\"]}')
print(f'Branch:   {r[\"default_branch\"]}')
print(f'Slug:     {r[\"suggested_slug\"]}')
"
```

Then create:

```bash
curl -s -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "<SUGGESTED_ID>",
    "project_slug": "<SUGGESTED_SLUG>",
    "repo_owner": "<OWNER>",
    "repo_name": "<REPO>",
    "default_branch": "<BRANCH>",
    "git_provider": "<PROVIDER>",
    "task_source": "github",
    "workspace_server_ids": [<SERVER_IDS>]
  }'
```

### Update Project

```bash
curl -s -X PUT http://localhost:8000/api/projects/<PROJECT_ID> \
  -H "Content-Type: application/json" \
  -d '{<FIELDS_TO_UPDATE>}'
```

## Notes

- Project IDs are typically `owner-repo` format (lowercase, hyphens)
- `task_source` options: github, gitea, gitlab, plane, manual
- `git_provider` options: github, gitea, gitlab, bitbucket
- Projects need at least one workspace server to run tasks
- Use `/autodev-launch` to launch agents on project workspaces

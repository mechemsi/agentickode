# ADR-003: Three Workspace Types

## Status

Accepted

## Context

Different projects need different workspace layouts:

- A **single-repo project** just needs a clone and a feature branch
- A **brand new project** needs scaffolding, git initialization, and a remote repository
- A **multi-repo ecosystem** (e.g., PrestaShop modules with a shared library) needs multiple clones plus a running application environment to test against

A one-size-fits-all workspace approach would either be too simple for complex scenarios or too complex for simple ones.

## Decision

**Support three workspace types: `existing`, `new`, and `cluster`.**

| Type | Path Convention | What Happens |
|------|----------------|--------------|
| `existing` | `/workspaces/{project_id}/` | Clone single repo, create feature branch |
| `new` | `/workspaces/{project_id}/` | Scaffold from template, git init, push to Gitea |
| `cluster` | `/workspaces/{task_id}/` | Clone N repos into subdirs, start sandbox Docker env |

Key design choices:
- **Cluster uses `{task_id}` not `{project_id}`** — multiple concurrent tasks on the same project need isolated workspaces
- **Sandbox templates are separate from the workflow code** — stored in `docker/sandboxes/` as standalone Docker Compose files
- **Mount injection via override file** — the system generates `docker-compose.override.yml` to map cloned repos into the sandbox container, keeping the template generic

## Consequences

**Benefits:**
- Simple projects stay simple — most repos only need `existing` type with no extra config
- Complex ecosystems get first-class support with sandboxes and multi-repo cloning
- Sandbox templates are reusable across projects (e.g., multiple PrestaShop modules share `prestashop-1.7` template)
- New project scaffolding automates the tedious repo-creation ceremony

**Trade-offs:**
- Three code paths in `setup_workspace` activity — more logic to maintain and test
- Cluster workspace cleanup must stop sandbox containers — forgetting this leaks resources
- Sandbox templates must be kept up to date with upstream application versions
- The `new` type creates repos on Gitea via API — requires appropriate permissions

**Mitigations:**
- Default is `existing` — projects with no `workspace_config` just work
- Sandbox cleanup is part of the finalization phase in the Temporal workflow
- Templates are versioned in the repo and easy to update

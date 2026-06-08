---
title: Multiple Workspace Folders + Single Projects on Platform Server
status: planned
date: 2026-06-08
related:
  - decisions/003-workspace-types.md
  - implementations/2026-06-05-pr-review-trigger.md
---

## Goal

Allow the local "platform" workspace server (`server_type="local"`) to hold **multiple workspace folder roots**, so that projects spread across different directories on the host can all be scanned, discovered, and assigned to that server — mirroring the multi-folder experience in autodev (the user's reference IDE-side workflow).

Also ensure the existing **single-project / `local_path`** shortcut continues to work without change.

---

## Scope

### In scope
- Add a `workspace_folders` JSONB column (`list[str]`) to `workspace_servers` that stores extra scan roots beyond the primary `workspace_root`.
- On scan (`POST /workspace-servers/{id}/scan`) and deploy-key, iterate **all folders** (primary + extra) and accumulate discovered projects.
- Surface the same Docker container list (via `DockerService`) that is already working for any server — no new work needed, confirmed present at `GET /workspace-servers/{id}/docker/overview`.
- Frontend: let the user add/remove extra workspace folders for any server (initially most useful for the platform server); update `WorkspaceServerForm` and `WorkspaceServerUpdate` schema.
- Single-project `local_path` path: no changes; already works and is out of scope.

### Out of scope
- Changing how the worker actually resolves a task's working directory (workspace setup phase already handles `local_path` and relative paths against `workspace_root`).
- Worker user / SSH key management for remote servers.
- Cluster / multi-repo workspace type (ADR-003) — separate concern.
- Making `workspace_root` itself nullable (keep as required fallback).

---

## Context: What "Like Autodev" Means (assumptions)

The Notion task says "same working as autodev". Based on codebase inspection:

| Assumption | Evidence |
|---|---|
| "Host docker list" is already surfaced | `DockerService` + `docker_management.py` work for the platform server via `LocalCommandService`; `executor_for_server` routes `server_type=local` to `LocalCommandService` |
| "Multiple workspace folders" means multiple scan roots | `ProjectDiscoveryService.scan_workspace(root)` is called once per scan with `server.workspace_root`; no multi-root support exists today |
| "Single projects" means `local_path` per project | `ProjectConfig.local_path` (migration 038) lets a project point at an already-checked-out path; `workspace_setup.py` skips clone when set |
| Platform server is id 6 in production | Seeded by `seed_platform_server()` with `server_type="local"`; actual id varies per DB |

**Open questions** (clarify before coding):
1. Should extra workspace folders also apply to remote SSH servers, or only the local platform server?
2. Should a newly discovered project found in folder B automatically link to the platform server (same as current `scan_workspace` behavior)?
3. When `workspace_root` is one of the extra folders, should scan deduplicate it?
4. What does "support single projects" concretely add beyond the existing `local_path` field — does the user want a simpler UI shortcut on the platform server card?

---

## Current Data Model (as found)

```
WorkspaceServer
  workspace_root: Text  -- single scan root, e.g. "/home/domas/projects"

ProjectConfig
  workspace_path: Text | null  -- relative path or absolute; resolved against workspace_root
  local_path:     Text | null  -- absolute pre-existing checkout; skips clone (migration 038)

ProjectWorkspaceServer (join table)
  project_id, workspace_server_id, priority
```

`ProjectDiscoveryService.scan_workspace(root)` does a `find {root} -maxdepth 2 -name .git`. It is called:
- `workspace_servers_discovery.py` `POST /scan` (line 178): once, against `server.workspace_root`
- `workspace_servers_discovery.py` `POST /deploy-key` (line 90): once, same
- `_setup_steps.py` `_step_discover` (line 192): once, during setup

---

## Technical Approach

### 1. Data model change

Add to `WorkspaceServer`:
```python
workspace_folders = Column(JSONB, nullable=True)
# Stores: ["path1", "path2", ...] or null
# workspace_root remains the primary / fallback root.
```

**No breaking change**: existing `workspace_root` stays; `workspace_folders` is additive.

### 2. Migration (migration 041)

```sql
ALTER TABLE workspace_servers
  ADD COLUMN workspace_folders JSONB;
-- default null → existing servers unaffected
```

### 3. Backend schema changes

`WorkspaceServerCreate` / `WorkspaceServerUpdate` (both in `backend/schemas/servers.py`):
```python
workspace_folders: list[str] | None = None
```

`WorkspaceServerOut` / `WorkspaceServerDetail`:
```python
workspace_folders: list[str] | None = None
```

### 4. Scan / discover change

Extract a helper in `workspace_servers_discovery.py`:

```python
def _all_roots(server: WorkspaceServer) -> list[str]:
    roots = [server.workspace_root]
    extra = server.workspace_folders or []
    for f in extra:
        if f not in roots:
            roots.append(f)
    return roots
```

Replace the two `proj_discovery.scan_workspace(server.workspace_root)` calls with:
```python
for root in _all_roots(server):
    discovered = await proj_discovery.scan_workspace(root)
    # ... existing upsert logic unchanged ...
```

Same pattern in `_setup_steps.py` `_step_discover`.

### 5. Workspace readiness check

`backend/api/projects.py` `check_workspace_readiness` resolves `expected_path` using `server.workspace_root`. No change needed there — that path is per-project (already stored in `project.workspace_path`).

### 6. Frontend

**`WorkspaceServerForm.tsx`** — add a dynamic list UI below the existing `workspace folder` field:
- A read-only display of `workspace_root` (the primary folder, set on creation).
- An "Extra workspace folders" section: add / remove text-input rows bound to `workspace_folders` array.

**`WorkspaceServers.tsx`** — include `workspace_folders` in the initial form data when editing a server:
```ts
workspace_folders: s.workspace_folders ?? [],
```

**`frontend/src/types/servers.ts`** — add field:
```ts
workspace_folders?: string[] | null;
```

**`WorkspaceServerCreate` / `WorkspaceServerUpdate`** in `frontend/src/api/servers.ts` — pass through `workspace_folders`.

---

## Files to Touch

| File | Change |
|---|---|
| `backend/models/servers.py` | Add `workspace_folders = Column(JSONB, nullable=True)` to `WorkspaceServer` |
| `backend/schemas/servers.py` | Add `workspace_folders` field to Create/Update/Out schemas |
| `backend/repositories/workspace_server_repo.py` | No structural change; `update()` already does `setattr` for any field |
| `backend/api/servers/workspace_servers_discovery.py` | Replace single `scan_workspace` calls with multi-root loop |
| `backend/services/workspace/_setup_steps.py` | Same multi-root loop in `_step_discover` |
| `alembic/versions/041_multi_workspace_folders.py` | New migration: ADD COLUMN workspace_folders JSONB |
| `backend/main.py` | ADD COLUMN IF NOT EXISTS in the inline migration guard (idempotent) |
| `frontend/src/types/servers.ts` | Add `workspace_folders?: string[] \| null` |
| `frontend/src/components/servers/WorkspaceServerForm.tsx` | Extra folders UI list |
| `frontend/src/pages/WorkspaceServers.tsx` | Pass `workspace_folders` in edit initial values |

---

## Coupling / Overlap Notes

- **"host-default-workspace" / platform server area**: `seed_platform_server.py` seeds `workspace_root="/workspaces"`. The new `workspace_folders` column would let operators add their local project directories without changing `workspace_root`. These two features operate on the same `WorkspaceServer` row.
- **ADR-003 cluster workspaces**: `workspace_root` is used in `workspace_setup.py` to resolve run paths. `workspace_folders` is purely for scan/discovery and does not affect how running tasks resolve their working directory.
- **`_helpers.get_workspace_server`** and the worker pipeline: no change — the pipeline uses the already-stored `task_run.workspace_path`, not `workspace_folders`.

---

## Success Criteria

- [ ] Migration 041 runs cleanly on an existing database (ADD COLUMN IF NOT EXISTS pattern; see migration 039 for precedent).
- [ ] `POST /workspace-servers/{id}/scan` with a server that has `workspace_folders = ["/home/domas/projects", "/home/domas/work"]` discovers git repos from both directories.
- [ ] A project whose repo lives in a folder not under `workspace_root` is correctly created/linked after scan.
- [ ] The platform server (local) Docker overview continues to work unchanged after the migration.
- [ ] `WorkspaceServerForm` allows adding/removing extra folder paths in the UI.
- [ ] Editing a server with existing `workspace_folders` pre-fills the list.
- [ ] `workspace_folders = null` (existing servers) behaves identically to today.
- [ ] Unit test: `_all_roots` deduplication (root already in extra list → returned once).
- [ ] `ruff`, `pyright`, ESLint pass on all changed files.

---

## Risks / Open Questions

| Risk / Question | Mitigation / Clarification needed |
|---|---|
| "Like autodev" is ambiguous — does it mean a VSCode-style multi-root workspace UX or just scan from more directories? | **Clarify with user** before implementing UI. Backend scan change is safe either way. |
| `find -maxdepth 2` may miss deeply nested repos | Out of scope; can be a follow-up config option |
| Scanning many roots on a slow filesystem could time out the scan endpoint | Parallelize with `asyncio.gather`; current 30s timeout per `_run` command may need adjustment |
| Platform server's `workspace_root` defaults to `/workspaces` (Docker internal path) — extra folders needed for host paths mounted into the container | This is precisely the use case; no risk if mount is in place |
| Single-project support: if user means "pin a project to a specific folder without a full scan", `local_path` already covers this on `ProjectConfig`. May need a clearer UI entry point | Could add a shortcut in `ProjectsPanel` to set `local_path` for platform server projects — evaluate after clarifying |

---

## Effort Estimate

Small–medium: ~1 day.
- Migration + model + schema: ~1h
- Backend scan loop + helper: ~1h
- Frontend form UI (dynamic list): ~2h
- Tests + lint pass: ~1h

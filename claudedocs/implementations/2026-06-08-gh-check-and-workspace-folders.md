---
title: gh CLI health check + multiple workspace folders
status: implemented
date: 2026-06-08
related:
  - claudedocs/plans/2026-06-08-host-default-workspace.md
  - claudedocs/plans/2026-06-08-multi-workspace-folders.md
---

# gh CLI health check + multiple workspace folders

Two safe, additive slices from the combined T2/T3/T4 effort. The risky host-execution
core of T2 (SSH-to-host) and the terminal/chat run-as-user work (T3) are deferred pending
an environment decision (see the host-default-workspace plan).

## What was built

### 1. `gh` CLI health check (T2, section 3)
On-demand check of whether the GitHub CLI is installed and authenticated on a workspace
server (runs as the server's `worker_user` when set, matching how runs execute).

| File | Change |
|------|--------|
| `backend/services/git/access_service.py` | `GhCliStatus` dataclass + `check_gh_cli()` — `command -v gh`, then `gh api user --jq .login` (stable JSON; relies on ambient `GITHUB_TOKEN`, no token on the command line) |
| `backend/schemas/git.py` | `GhCliCheckResult` (installed/auth_ok/auth_user/error) |
| `backend/api/servers/git_access.py` | `POST /workspace-servers/{id}/git-access/check-gh` |
| `frontend/src/api/servers.ts` | `checkGhCli(id)` |
| `frontend/src/components/servers/GitAccessPanel.tsx` | "GitHub CLI (gh)" row with Check button + status badge |
| `tests/unit/test_git_access_service.py` | `TestCheckGhCli` (installed/authed, not-installed, not-authed, runs-as-worker) |

### 2. Multiple workspace folders (T4)
A server can hold extra scan roots beyond `workspace_root`; scan/discovery iterates all of them.

| File | Change |
|------|--------|
| `backend/models/servers.py` | `workspace_folders` JSONB column (nullable, additive) |
| `alembic/versions/041_workspace_folders.py` | migration 040→041 (`ADD COLUMN IF NOT EXISTS`) |
| `backend/main.py` | runtime auto-migrate guard for the column |
| `backend/schemas/servers.py` | `workspace_folders` on Create/Update/Out |
| `backend/api/servers/workspace_servers_discovery.py` | `_all_roots()` (dedup) + `_scan_all_roots()`; both scan call sites accumulate across roots |
| `backend/services/workspace/_setup_steps.py` | `_step_discover` scans all roots |
| `frontend/src/types/servers.ts` | `workspace_folders?` on WorkspaceServer/Create; `GhCliCheckResult` type |
| `frontend/src/components/servers/WorkspaceServerForm.tsx` | dynamic add/remove "extra workspace folders" list |
| `frontend/src/pages/WorkspaceServers.tsx` | pre-fill `workspace_folders` when editing |
| `tests/unit/test_workspace_folders_scan.py` | `_all_roots` dedup + `_scan_all_roots` accumulation |

## Verification
- Backend: new unit tests pass; full suite green; ruff + pyright clean; migration 041 applies (040→041) and the column is present.
- Frontend: 61 tests across the 5 affected suites pass; eslint + tsc clean.

## Deferred (needs decision)
- **Host execution (T2 core):** make the platform server target the real host via SSH to
  `host-gateway`. Blocked on WSL2/Docker-Desktop environment setup (host `sshd`, authorized
  key, `runuser` root). Flipping the working in-container server is risky — left off by default.
- **Run-as-user for terminal + chat (T3):** depends on the host run-as-user model above.

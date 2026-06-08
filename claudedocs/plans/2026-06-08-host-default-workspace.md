---
title: "Host Machine as Default Platform Workspace (run-as user + gh check)"
status: planned
date: 2026-06-08
related:
  - plans/2026-05-24-workspace-config.md
  - decisions/003-workspace-types.md
---

# Host Machine as Default Platform Workspace

## Goal

Make the built-in "platform" workspace server represent the **actual host machine** (not the backend container), pin all task execution to a single chosen OS user on that host, and surface a `gh` CLI health check that confirms GitHub access is functional.

---

## Scope

### In Scope
- Change the "platform" server so execution targets the host, not the backend container
- User selection: the `worker_user` field on the platform server configures which OS account everything runs as (same model as all other servers — no new primitives)
- `gh` availability + auth check: new method in `GitAccessService` + new API endpoint; surface in the Git Access panel for the platform server
- Seed update: `seed_platform_server` sets a sensible default `worker_user` (e.g. derived from `$USER` at startup time, or configurable via env)
- Migration 041 to add a `gh_enabled` status column to `workspace_servers` (optional, see Data Model section)

### Out of Scope
- Supporting multiple per-project host users (the task says "single user")
- Changing how remote SSH servers work
- SSH key management for the host connection (the chosen approach handles this differently than SSH)
- Any changes to the worker pipeline phases themselves (they already use `run_command_as(server.worker_user, ...)`)

---

## Technical Approach

### 1. The Core Problem: Container vs Host

Currently `executor_for_server(server)` returns `LocalCommandService()` for `server_type="local"`. `LocalCommandService.run_command()` runs `asyncio.create_subprocess_shell(...)` **inside the backend container** — not on the host.

The task asks for execution on the host machine. There are four architectural options:

| Option | Mechanism | Pros | Cons |
|--------|-----------|------|------|
| **A. SSH loopback to host** | Add `extra_hosts: ["host-gateway:host-gateway"]` to docker-compose; platform server becomes `server_type="remote"` with `hostname="host-gateway"`, auth via shared SSH key | Clean: reuses `SSHService` unchanged; full `run_command_as` via `runuser`; isolated from container FS | Requires SSH daemon on host; SSH key deployment ceremony; adds latency; two auth hops for security analysis |
| **B. Docker socket + `docker run --network=host`** | Execute commands by spawning ephemeral containers via the already-mounted `/var/run/docker.sock` | Reuses existing socket mount | Command output streaming is awkward; not truly "host" (still namespaced); security surface is large |
| **C. `nsenter` via Docker socket** | Mount docker socket, get host PID 1, `nsenter --target 1 --mount --uts --ipc --net --pid` | Direct host execution | Requires `--privileged` or extensive capabilities; very dangerous; rejected |
| **D. Keep `LocalCommandService`, add `run_command_as` via `runuser` but with host filesystem mounts** | Mount host directories into container; run as the specified user via `runuser` inside container | No SSH overhead; simple | Container runs as root so `runuser` works; workspaces must be on a mounted host path; doesn't truly "escape" the container's mount namespace |

**Recommended approach: Option A — SSH to `host-gateway`.**

Rationale grounded in the codebase:
- `SSHService` already supports `run_command_as(user, cmd)` via `runuser -l` (line 76 of `ssh_service.py`)
- `WorkerUserService.setup()` already does all the credential plumbing for any SSH target
- The docker-compose files already mount `/var/run/docker.sock`, but not for SSH — Option B would need new code
- Both `docker-compose.yml` and `docker-compose.dev.yml` do **not** currently set `extra_hosts`; adding `host-gateway:host-gateway` is a one-line docker-compose change
- The myDash reference in `worktree.py` comment (line 7) notes myDash used `setpriv --reuid=1000` for host-side execution; the equivalent here is SSH + `runuser`

**When NOT running in Docker** (bare-metal install): the platform server should remain `server_type="local"` with `LocalCommandService` but with `run_command_as` wrapping via `runuser`. `LocalCommandService.run_command_as` already does this (line 56 of `local_command_service.py`).

This means the platform server needs a runtime-detected mode:

```
IS_DOCKERIZED = os.path.exists("/.dockerenv")
```

- If dockerized → platform server uses SSH to `host-gateway` (Option A)
- If bare-metal → platform server keeps `server_type="local"`, but `worker_user` is still respected via `runuser`

### 2. Run-As User Model

The model is already implemented for all remote servers — `WorkspaceServer.worker_user` column, `WorkerUserService`, and `run_command_as` in both `SSHService` and `LocalCommandService`. The platform server just needs:

1. `worker_user` seeded to a meaningful default at startup
2. The seed to read `PLATFORM_USER` env var (new, optional) or fall back to `os.environ.get("USER", "root")`
3. UI: the platform server card in `WorkspaceServers.tsx` already hides SSH fields when `server_type === "local"` (`isLocal` prop on `WorkspaceServerForm`). The `worker_user` input is already shown for local servers (it is outside the `!isLocal` block, line 116 of `WorkspaceServerForm.tsx`).

No new data model needed for the user selection itself.

### 3. `gh` CLI Check

**Where it lives:** `GitAccessService` (`backend/services/git/access_service.py`) — add a new async method:

```python
async def check_gh_cli(self, as_user: str | None = None) -> GhCliStatus:
    """Check gh CLI availability and whether GITHUB_TOKEN auth works."""
    # 1. command -v gh
    # 2. GITHUB_TOKEN=... gh auth status (or gh api user)
    # 3. parse output for "Logged in to github.com as ..."
```

`gh` is already installed in the backend container (`Dockerfile.backend.dev` lines 13–14) and in remote workspace servers via `_install_system_deps` (`_setup_steps.py` lines 269–283). The `_try_gh_pr_create` function in `approval.py` already does a `command -v gh` check (line 147). The new method formalises this as a health check.

**API surface:** New endpoint in `backend/api/servers/git_access.py`:

```
POST /workspace-servers/{server_id}/git-access/check-gh
```

Returns a schema like:

```python
class GhCliCheckResult(BaseModel):
    installed: bool
    auth_ok: bool
    auth_user: str | None = None
    error: str | None = None
```

**Frontend:** Add a "GitHub CLI" row to `GitAccessPanel.tsx` (already fetches git-access data per server). Show `gh` installed/auth status badge alongside the SSH provider badges. Only render this row when the platform server is selected (or always — it's useful for any server).

**`GITHUB_TOKEN` handling:** `gh` authenticates via `GITHUB_TOKEN` env var (no interactive `gh auth login` needed). The token is already written to `.agentickode_env` by `WorkerUserService._build_env_vars` for worker users on remote servers (lines 187–190 of `worker_user_service.py`). For the platform server's worker user, the same mechanism applies. The check should source this env file before calling `gh auth status`.

### 4. `seed_platform_server` Changes

Current seed (`backend/seed/platform_server.py`):
- Creates server with `username="root"`, no `worker_user`
- Hostname: `"localhost"`, `server_type="local"`, `port=0`

Proposed changes:
1. Read `PLATFORM_USER` env var (add to `config.py` as `platform_user: str = ""`); fall back to `os.environ.get("USER", "root")`
2. If dockerized and SSH-to-host approach chosen: update `server_type` to `"remote"`, `hostname` to `"host-gateway"`, `port` to `22`, `username` to `root` (the container user that has the SSH key)
3. Set `worker_user` to the resolved platform user
4. If not dockerized: keep `server_type="local"`, set `worker_user` to the resolved platform user

The seed is idempotent (checks `server_type == "local"`) — it should also update the `worker_user` field on subsequent runs if not yet set.

### 5. Data Model / Migration

The `WorkspaceServer` model (`backend/models/servers.py`) already has `worker_user`, `worker_user_status`, `worker_user_error` columns. No new columns are strictly required for the user-selection feature.

For the `gh` check result, two lightweight options:

**Option 1 (no migration):** Store `gh` status in the existing `setup_log` JSONB column alongside other setup results. No schema change.

**Option 2 (migration 041):** Add `gh_cli_status` (Text, nullable) and `gh_cli_error` (Text, nullable) to `workspace_servers`. Provides queryable state but adds schema churn.

**Recommendation:** Use Option 1 (no migration) for the gh check — store in `setup_log`. Only add migration if the frontend needs to sort/filter by `gh_cli_status` across many servers. The check is on-demand anyway.

If the SSH-to-host approach is adopted, migration 041 would be needed to update the platform server's `server_type`, `hostname`, and `port` from `"local"/"localhost"/0` to `"remote"/"host-gateway"/22` — OR handle this in seed logic with an explicit UPDATE on startup.

---

## Coupling: Related Tasks

| Related task | Overlap |
|---|---|
| "Launch-as-user" | Uses the same `worker_user` field and `run_command_as` path. Any change to how the platform server's user is resolved must stay compatible with per-project `run_as` overrides (`ProjectConfig.worker_user_override` in `usernames.py` validation). |
| "Multi-workspace-folders" | Changes `workspace_root` derivation in `_step_create_workspace_dir` (`_setup_steps.py` line 94). If both tasks land together, the platform server's `workspace_root` must be a host-mounted path accessible to the chosen user. |
| PR review poller | Uses `executor_for_server` for the platform server to run git/gh commands. If the platform server switches from `LocalCommandService` to `SSHService`, PR poller executions will go over SSH to the host — verify latency is acceptable. |
| Worker pipeline phases | `_helpers.py:get_ssh_for_run` resolves the executor for any run's server. Platform-server runs will switch from subprocess to SSH if Option A is implemented. No phase code changes needed, but test coverage for platform-server runs should be updated. |

---

## Success Criteria

- [ ] Platform workspace server correctly represents the host machine in both deployment modes (Docker container and bare-metal)
- [ ] `worker_user` on the platform server is seeded from `PLATFORM_USER` env or `$USER` at startup
- [ ] Commands dispatched to the platform server (e.g. from a run targeting it) execute as the configured `worker_user` on the host, not as root inside the container
- [ ] `POST /workspace-servers/{id}/git-access/check-gh` returns `installed: true` and `auth_ok: true` when `GITHUB_TOKEN` is set and valid
- [ ] `GitAccessPanel` for the platform server shows a `gh` CLI status badge
- [ ] Existing SSH remote servers are unaffected
- [ ] `seed_platform_server` is idempotent: re-running on an existing DB row updates `worker_user` and `hostname` without duplicating the row
- [ ] All backend tests pass; targeted tests cover the new `check_gh_cli` method and seed logic

---

## Risks and Open Questions

| # | Risk / Question | Severity | Notes |
|---|---|---|---|
| 1 | **SSH daemon on host required (Option A)** — most dev setups (WSL2, macOS Docker Desktop) do not have `sshd` running on the host. This is a non-trivial prerequisite and breaks the "just run docker compose up" experience. | High | Mitigates by: detect `/.dockerenv` and gracefully fall back to `LocalCommandService` if SSH to `host-gateway` fails; provide a clear setup guide. |
| 2 | **`host-gateway` IP differs by Docker installation** — Linux: `172.17.0.1` (bridge default); Docker Desktop macOS/Windows: uses `host-gateway` magic DNS; WSL2: depends on WSL network mode. The `extra_hosts: host-gateway:host-gateway` docker-compose stanza works on Linux Docker Engine and Docker Desktop but not all WSL2 configurations. | Medium | Must be documented; consider fallback to configurable `PLATFORM_SSH_HOST` env var. |
| 3 | **SSH key setup ceremony** — the container must have an SSH private key that is authorized on the host. Currently `.ssh/` is mounted into the container but the host's `~/.ssh/authorized_keys` may not include the container's key. | High | Seed could auto-generate a key and print the public key to logs with instructions; or require a one-time manual `ssh-copy-id` step. |
| 4 | **`runuser` requires root on host** — `run_command_as(user)` calls `runuser -l <user>`, which needs root privileges. If the SSH user connecting to the host is not root, `runuser` will fail. The workaround is `sudo runuser -l <user>` with NOPASSWD sudoers entry. | High | The existing remote-server pattern assumes SSH as root; same assumption must hold for platform server SSH. |
| 5 | **Bare-metal mode: `LocalCommandService.run_command_as` uses `runuser`** — on the host directly, this works fine if the process is root (e.g. system service). If run as a non-root user, `runuser` fails. | Medium | For bare-metal non-root installs, need `sudo` wrapping or restrict `worker_user` to the current user only. |
| 6 | **`gh auth status` output parsing** — `gh` output format can change across versions. The check should use `gh api user --jq .login` (JSON output, stable) rather than parsing human-readable `gh auth status`. | Low | Easy to fix if it breaks; use JSON flag. |
| 7 | **Platform server ID drift** — the task brief mentions "DB row id 6". The seed does NOT guarantee ID 6 (the ID is auto-incremented and depends on insert order). The seed uses `server_type == "local"` as the lookup key, which is correct. No code should hardcode ID 6. | Low | Confirm no frontend or backend code references platform server by literal ID. |
| 8 | **Container FS vs host FS path mismatch** — when running with Option A (SSH to host), `workspace_root` on the platform server must be a path that exists on the host, not a Docker volume path like `/workspaces`. The seed must derive or accept a host-side workspace path. | Medium | Add `PLATFORM_WORKSPACE_ROOT` env var as override; default to `~/agentickode-workspaces` on the host user's home. |
| 9 | **`GITHUB_TOKEN` availability inside the check** — the new `check_gh_cli` endpoint needs `GITHUB_TOKEN` in env when running the check. For the platform server's worker user, this is written into `~/.agentickode_env` by `WorkerUserService.setup()`. The check must source this file. If `WorkerUserService.setup()` has not been run for the platform server (common: it is currently skipped entirely for local servers), the env file may not exist. | Medium | Either (a) run `WorkerUserService.setup()` for the platform server on first use, or (b) inject `GITHUB_TOKEN` directly from `settings.github_token` in the check command. |
| 10 | **Scope creep with "multi-workspace-folders" task** — that task may change `workspace_root` derivation. Implementing both tasks in the same sprint without coordination risks merge conflicts in `_setup_steps.py` and `seed_platform_server`. | Low | Sequence: implement this task first; multi-workspace-folders can add its changes on top. |

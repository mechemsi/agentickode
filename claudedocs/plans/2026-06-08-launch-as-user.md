---
title: "Terminal + Chat Agent Launch as Selected User"
status: implemented
date: 2026-06-08
related:
  - plans/2026-05-24-workspace-config.md
  - decisions/003-workspace-types.md
---

# Terminal + Chat Agent Launch as Selected User

> **STATUS (2026-06-09): implemented** (all no-op when `worker_user` is unset).
> - **Terminal PTY** — `ws.py:_local_pty_terminal` runs `runuser -l <user> -c bash`.
> - **Chat agent** — `agent_process` wraps the command via `runuser`; temp files chowned to the
>   target uid (kept 0o600); `chat_service` resolves the user via `get_platform_run_as_user`.
> - **Local-terminal tmux** — `local_terminals.py` (create/resume/close) + `ws.py:_attach_to_tmux`
>   wrap every tmux op (`new-session`/`set-option`/`send-keys`/`attach`/`has-session`/`kill`) with
>   `runuser`; the chosen user is stored on `local_terminal_sessions.run_as_user` (migration 042)
>   so resume/attach use the same user (tmux server is per-user).
> - **LaunchAgentModal** — passes the server's `worker_user` (now on `WorkspaceReadinessItem`)
>   instead of hard-coded `"root"`.
>
> Activates once the platform server's `worker_user` is set (via `PLATFORM_USER`).

## Goal

Unify the launch context for the platform server: both the xterm.js terminal bridge and the chat-launched agent run as the `run_as_user` configured on the platform `WorkspaceServer`, exactly as worker-phase agents do on remote servers.

## Scope

### In scope
- `_local_pty_terminal` (used by `/ws/servers/{id}/terminal` when `server_type == "local"`) — run PTY as the selected user via `runuser`/`su`
- `/ws/local-terminal-attach/{tmux_name}` + `/ws/local-terminal/{agent}` — attach-to-tmux path runs the tmux session as the selected user
- `POST /api/local-terminals` (`local_terminals.py:create_local_session`) — create tmux session as the selected user
- `POST /api/local-terminals/{id}/resume` — resume tmux session as the selected user
- Chat-launched agents via `POST /api/chat/sessions` → `chat_service` → `agent_process.py:invoke_agent/invoke_agent_streaming` — subprocess spawned as the selected user
- Reading the run-as user from `WorkspaceServer.worker_user` for the platform server (same field already used by SSH path)

### Out of scope
- Remote SSH servers (already handled correctly via `runuser -l {worker_user}` in `ws.py:ws_terminal`, `session_service.py:_as_user`, etc.)
- The "host-default-workspace" task that decides **what value** `WorkspaceServer.worker_user` holds for server_id=6; this task only consumes that value
- Worker-phase agent launch (already correct via `ensure_agent_ready` + `CLIAdapter.worker_user`)
- The `LaunchAgentModal` → `createSession` → `SessionService` path (already respects `user_context`; caller just needs to pass `worker_user` instead of `"root"`)

## Context: Where Each Launch Happens Today

### Terminal bridge — `/ws/servers/{id}/terminal`

`ws.py:ws_terminal` (line 126) branches on `server_type`:

```
"local" → _local_pty_terminal(websocket)   # fork + exec("bash") as current process user = root
"remote" → SSHService + runuser -l {worker_user}
```

`_local_pty_terminal` at line 60–122 does `pty.fork()` → `os.execvp("bash", ["bash"])` in the child. No `setuid`/`su`/`runuser` — it runs as whatever user the backend process is (root inside Docker).

### Local terminal sessions (Chat page) — `/api/local-terminals`

`local_terminals.py:create_local_session` (line 71) calls `asyncio.create_subprocess_shell` for `tmux new-session` and `tmux send-keys`. Both run as root (the container process user). The `env` dict hard-codes `/root/.local/bin`.

The WebSocket attach path `_attach_to_tmux` (ws.py line 518) also uses `asyncio.create_subprocess_shell` — no user switching.

### Chat agent — `POST /api/chat/sessions`

`chat.py:create_session` → `chat_service.create_session` → messages trigger `invoke_agent` / `invoke_agent_streaming` in `agent_process.py`. Both call `asyncio.create_subprocess_shell(cmd_str, ...)` with `env = {**os.environ, ...}`. No user switching — runs as root.

### What the autodev/worker-phase path does correctly

`ws.py:ws_terminal` for remote servers wraps `shell_cmd` with `runuser -l {worker_user}` (line 338). `SessionService._as_user` (session_service.py line 27) wraps all tmux commands with `runuser -l {user}`. `ensure_agent_ready` sets `adapter.worker_user` so the CLI adapter runs the agent as that user.

## Technical Approach

### 1. Read the platform server's `worker_user` once

A small helper in `backend/services/workspace/local_command_service.py` (or a new `backend/services/workspace/platform_user.py`):

```python
async def get_platform_run_as_user(db: AsyncSession) -> str | None:
    """Return WorkspaceServer.worker_user for the local platform server, or None."""
    result = await db.execute(
        select(WorkspaceServer.worker_user)
        .where(WorkspaceServer.server_type == "local")
        .limit(1)
    )
    return result.scalar_one_or_none()
```

All three surfaces call this (or receive it as a parameter) to know which user to switch to.

### 2. Fix `_local_pty_terminal` (ws.py line 60)

Replace the bare `os.execvp("bash", ["bash"])` child exec with a `runuser`-based exec when a `run_as_user` is set:

```python
if run_as_user:
    os.execvp("runuser", ["runuser", "-l", run_as_user, "-c", "bash"])
else:
    os.execvp("bash", ["bash"])
```

The `ws_terminal` endpoint already receives `server_id`; fetch `server.worker_user` before calling `_local_pty_terminal`. Pass it as a parameter:

```python
# ws.py:ws_terminal — local branch
run_as_user = server.worker_user  # None → run as root (current behaviour)
await _local_pty_terminal(websocket, run_as_user=run_as_user)
```

### 3. Fix local-terminal tmux sessions (local_terminals.py + ws.py `_attach_to_tmux`)

**Create session** (`local_terminals.py:create_local_session`):
- Accept an optional `run_as_user: str | None` resolved from `WorkspaceServer.worker_user`.
- Wrap the `tmux new-session` shell command with `runuser -l {run_as_user} -c {quoted_cmd}` when non-None.
- Wrap `tmux send-keys` the same way.
- Update the hard-coded `/root/.local/bin` PATH to `$HOME/.local/bin` (resolved relative to the user) or use `f"/home/{run_as_user}/.local/bin"`.

The `CreateSessionRequest` from Chat.tsx currently has no `run_as_user` field. Two options:
- **Option A (preferred):** The backend resolves `run_as_user` from the platform `WorkspaceServer.worker_user` — no frontend change needed.
- **Option B:** Add an optional `run_as_user` field to `CreateSessionRequest` / `SessionOut` and pass it from the frontend.

Prefer Option A for the platform-local path; Option B only if per-session overrides are needed.

**Resume session** (`local_terminals.py:resume_local_session`): same wrapping pattern as create.

**Attach** (`ws.py:_attach_to_tmux`): the `tmux attach-session` subprocess needs to run as the user who owns that tmux session. Wrap `tmux attach-session -t {tmux_name}` with `runuser -l {run_as_user} -c ...` via a sub-PTY or use `su -l {user} -c "tmux attach..."`.

Alternative for attach: since the tmux session itself runs as `run_as_user`, a simpler approach is to run the `tmux attach` directly as that user using `runuser` in the `attach_proc` command line rather than relying on the current user.

**Schema change**: `LocalTerminalSession` model does not store the `run_as_user`. It should be persisted so resume can use it without hitting the DB for the platform server again.

### 4. Fix chat agent launch (agent_process.py)

`invoke_agent` and `invoke_agent_streaming` both build a `cmd_str` and call `asyncio.create_subprocess_shell`. Wrap the shell invocation with `runuser -l {user} -c {quoted_cmd}` when `run_as_user` is provided:

```python
if run_as_user:
    cmd_str = f"runuser -l {shlex.quote(run_as_user)} -c {shlex.quote(cmd_str)}"
```

Add `run_as_user: str | None = None` parameter to both `invoke_agent` and `invoke_agent_streaming`. `ChatService.send_message` / `send_message_streaming` need to pass it down; `ChatService.create_session` resolves it from the platform server once (or stores it on `ChatSession`).

The MCP config temp file (`_write_mcp_config`) and message temp file are written by the backend process (root); `runuser` inherits the path, so the temp files must be readable by `run_as_user` — use `chmod o+r` or write to `/tmp` (already the case via `tempfile.mkstemp`). `/tmp` files created by root with default umask (0o600) are not readable by other users; change to 0o644 or use `chmod` after creation.

### 5. LaunchAgentModal path — pass `worker_user` instead of `"root"`

`LaunchAgentModal.tsx` line 48 hard-codes `user_context: "root"`. This path goes through `SessionService._as_user`, which already respects the `user` parameter — but currently `"root"` means no `runuser` wrapping. Change the frontend to pass `user_context: ws.worker_user ?? "root"` where `ws` is the `WorkspaceReadinessItem`. This requires `WorkspaceReadinessItem` to expose `worker_user`.

Alternatively (cleaner): the backend `/sessions` `POST` handler already calls `_build_session_service(server, user=body.user_context)`. If the frontend omits `user_context`, default it to `server.worker_user` in the backend.

## Configuration: Where "Selected User" Comes From

The source of truth is `WorkspaceServer.worker_user` for the platform server (seeded in `seed_platform_server.py`). The **host-workspace task** is responsible for ensuring this field is set to the correct run-as user on the local server record. This task reads it and acts on it — the two tasks are cleanly decoupled.

No new columns are needed. The only model change is optionally adding `run_as_user: str | None` to `LocalTerminalSession` so resume doesn't need to re-query the server.

## Coupling / Dependency

This task **requires** the host-workspace task to have populated `WorkspaceServer.worker_user` (for `server_type == "local"`) before the behaviour changes are visible. Until that task ships, `worker_user` is `NULL` and all paths fall through to the current root behaviour — so this task is safe to merge first (no-op when `worker_user` is unset).

## Files to Touch

| File | Change |
|------|--------|
| `backend/api/ws.py` | Pass `run_as_user=server.worker_user` to `_local_pty_terminal`; update `_local_pty_terminal` to exec `runuser`; wrap `_attach_to_tmux` subprocess with `runuser` |
| `backend/api/local_terminals.py` | Resolve `run_as_user` from platform server; wrap tmux create/send/resume; update PATH; persist `run_as_user` on `LocalTerminalSession` |
| `backend/services/chat/agent_process.py` | Add `run_as_user` param; wrap `cmd_str`; fix temp file permissions |
| `backend/services/chat/chat_service.py` | Resolve `run_as_user` from platform server; thread it into `invoke_agent*` |
| `backend/models/local_sessions.py` | Add `run_as_user: Column(Text, nullable=True)` |
| `backend/schemas/sessions.py` | Expose `run_as_user` in `LocalTerminalSession` schemas if needed |
| `frontend/src/components/projects/LaunchAgentModal.tsx` | Pass `worker_user` from readiness response as `user_context` |
| `frontend/src/types` (possibly) | Add `worker_user` to `WorkspaceReadinessItem` if not present |
| New migration | `ADD COLUMN IF NOT EXISTS run_as_user TEXT` on `local_terminal_sessions` |

## Success Criteria

- [ ] Opening `/ws/servers/{local_id}/terminal` from the UI starts a shell as `WorkspaceServer.worker_user` (not root) when `worker_user` is set
- [ ] `POST /api/local-terminals` creates a tmux session owned by `worker_user`; `tmux list-sessions` on the container shows it running under that user
- [ ] Chat agent invocation (`invoke_agent`) spawns the `claude` process as `worker_user`; `ps aux` in the container shows the process owned by that user
- [ ] When `WorkspaceServer.worker_user` is NULL, all three surfaces fall back to root (current behaviour — no regression)
- [ ] LaunchAgentModal sessions use `worker_user` instead of hard-coded `"root"`
- [ ] Temp files written for chat MCP config and message payload are readable by `worker_user`
- [ ] Resume of a closed local-terminal session re-launches as the same `run_as_user` that was originally stored

## Risks / Open Questions

| Risk | Mitigation |
|------|-----------|
| `runuser` requires root privileges — platform container must run as root (currently true) | Document assumption; verify in CI |
| `agent_process.py` temp files (`/tmp/agentickode-*`) are created with root umask (0o600); `runuser` child cannot read them | Change `os.fdopen` → `os.chmod(path, 0o644)` after creation, or write with `umask(0o022)` in context |
| `_attach_to_tmux` uses a PTY `pty.openpty()` bridged via `attach_proc`; wrapping with `runuser` changes stdin ownership for the PTY | Test that `runuser -l user -c "tmux attach-session -t name"` works correctly with PTY stdin |
| `LocalTerminalSession` has no `run_as_user` column — resume path would need to re-query the platform server | Add the column (migration) or accept re-query overhead |
| If `worker_user` changes after sessions are created, existing sessions remain under the old user | Acceptable; document that sessions inherit the user at creation time |
| Chat sessions store `agent_session_id` for `--resume`; if `worker_user` changes between messages, `--resume` may fail (session history in a different user's home dir) | Resolve user at session-creation time and store on `ChatSession`; do not re-resolve per message |

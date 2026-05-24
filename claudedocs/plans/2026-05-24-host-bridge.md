---
title: Host bridge — run agents on the WSL host from the Docker backend
status: planned
date: 2026-05-24
related:
  - claudedocs/plans/2026-05-24-workspace-config.md
---

## Goal

Make the backend container reach out to the developer's host (typically
WSL on Windows, but the design is OS-agnostic) and execute the chat /
terminal / workflow agent there — not in the container. The host's
``domas`` user, host's Claude install, host's project folders.

## Why

Today the "local platform server" is a misnomer: ``LocalCommandService``
just runs ``asyncio.create_subprocess_*`` *inside the backend container*.
The host-side ``domas`` user and host-side ``claude`` binary are
unreachable. With the workspace-config patch ([[2026-05-24-workspace-config]])
the operator can drop to a non-root user — but only one that exists in
the container, with a Claude config we copy from ``/root``. That doesn't
match what the user actually wants on a developer machine.

## Architecture

```
┌─ Browser (xterm.js) ──────────┐
│                               │
└──[ws/local-terminal-attach]──→│
                                ▼
┌─ Backend (Docker container) ─────────────────┐
│                                              │
│  ChatService ──→ HostBridgeService ──HTTP──→ │
│  WS attach ────→ HostBridgeService ──WS────→ │
│                                              │
└─────────────────────────────────────┬────────┘
                                      │  host.docker.internal:17777
                                      │  Bearer <token>
                                      ▼
                            ┌─ Host bridge daemon ──────────────┐
                            │  scripts/host_bridge.py           │
                            │  Runs as domas on WSL host        │
                            │                                   │
                            │  POST /exec → subprocess          │
                            │  WS   /pty  → pty.fork + tmux     │
                            └───────────────────────────────────┘
```

### Daemon (`scripts/host_bridge.py`)

* Single FastAPI app, ~200 lines.
* Listens on ``127.0.0.1:17777`` (configurable via ``--port``).
* Bearer-token auth on every request. Token is generated on first start
  and written to ``~/.agentickode/host-bridge.token`` (mode 0600); the
  user pastes that token into the platform server config in the UI.
* Endpoints:
  * ``POST /exec`` — one-shot subprocess. Body:
    ``{"cmd": str, "env": dict, "cwd": str|null, "timeout": int}``.
    Response: ``{"stdout": str, "stderr": str, "exit_code": int}``.
  * ``WS /pty`` — PTY-backed tmux session. First message from client is
    ``{"cmd": str, "cols": int, "rows": int, "env": dict}``; subsequent
    messages are ``{"type": "input"|"resize", ...}`` to/from the PTY.
* Runs as the host user (``domas``) — no privilege drop inside; the
  user starts the daemon under their own account.

### Backend service (`backend/services/workspace/host_bridge_service.py`)

* New ``HostBridgeService`` implementing the ``CommandExecutor`` protocol
  (``run_command``, ``run_command_stream``, ``fire_and_forget``,
  ``test_connection``).
* Reads ``bridge_url`` + decrypted ``bridge_token_enc`` from the
  ``WorkspaceServer`` record (see migration below).
* Uses ``httpx`` (already a dependency) for HTTP; ``websockets`` for
  the PTY path. ``websockets`` is a small new dep — added to
  ``requirements.txt``.

### Dispatch

* ``executor_for_server`` (in ``command_executor.py``) adds a third
  branch: ``server_type == "local"`` AND ``bridge_url`` set → return
  ``HostBridgeService``. Falls back to today's ``LocalCommandService``
  when no bridge is configured (so existing setups keep working).

### UI

* Platform server form gains two fields (hidden for remote servers via
  the existing ``isLocal`` prop, inverted):
  * ``Bridge URL`` (e.g. ``http://host.docker.internal:17777``)
  * ``Bridge Token`` (password-style input; backend stores encrypted)
* New "Bridge status" indicator on the platform server card — pings
  ``GET /health`` on the bridge URL with the token, shows
  green/yellow/red.

### Migration 039

```python
op.add_column("workspace_servers",
    sa.Column("bridge_url", sa.Text(), nullable=True))
op.add_column("workspace_servers",
    sa.Column("bridge_token_enc", sa.Text(), nullable=True))
```

Both nullable; existing rows keep ``LocalCommandService`` behavior.

## Out of scope (this phase)

* Auto-start of the daemon (systemd / WSL init). Operator runs
  ``make host-bridge`` (or ``python scripts/host_bridge.py``) once per
  WSL session for now.
* Worktree-via-bridge for the full workflow pipeline. We wire chat +
  terminal first since those are what the user is actively running.
  ``workspace_setup`` will follow once the executor abstraction is
  stable.
* Windows/Mac native support. WSL on Windows is the target; the daemon
  itself is OS-agnostic but we don't auto-detect the bridge URL there.

## Test plan

* Daemon unit tests using FastAPI's TestClient (token auth, exec,
  PTY echo round-trip).
* ``HostBridgeService`` tests with a mocked httpx + websockets client.
* End-to-end manual smoke:
  1. ``make host-bridge`` on WSL host (daemon starts, prints token).
  2. UI → Platform server → Edit → paste bridge URL + token → Save.
  3. New chat session → ``whoami`` reads ``domas``; ``which claude``
     points at host Claude.

## Success criteria

- [ ] ``whoami`` inside a chat / terminal returns the host user.
- [ ] ``which claude`` points at the host Claude binary.
- [ ] Files created during a chat live in the operator's host
      project folder with correct host UID/GID.
- [ ] When ``bridge_url`` is empty, behavior is unchanged from today
      (in-container subprocess).
- [ ] Token auth rejects bad/missing tokens with 401.

## Phases

1. **Daemon + ``HostBridgeService.run_command``** (this PR scope start)
2. **Chat path through bridge** (this PR)
3. **WS PTY through bridge** (this PR — terminal is the demo)
4. **Migration + UI** (this PR)
5. **Pipeline integration** (follow-up)

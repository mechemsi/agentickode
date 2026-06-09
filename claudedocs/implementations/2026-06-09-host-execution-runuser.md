---
title: Platform run-as-user (terminal + chat) + SSH-to-host scaffolding
status: implemented
date: 2026-06-09
related:
  - claudedocs/plans/2026-06-08-launch-as-user.md
  - claudedocs/plans/2026-06-08-host-default-workspace.md
  - claudedocs/runbooks/platform-host-execution.md
---

# Platform run-as-user + SSH-to-host scaffolding

Continues the T2/T3 effort. Everything here is **no-op / OFF by default** — unset config and a
NULL `worker_user` keep the current in-container-root behaviour (zero regression).

## What was built

### Run-as user — terminal + chat (T3, partial)
| File | Change |
|------|--------|
| `backend/api/ws.py` | `_local_pty_terminal(run_as_user)` execs `runuser -l <user> -c bash`; `ws_terminal` passes the platform server's `worker_user` |
| `backend/services/chat/agent_process.py` | `_wrap_runuser` + `_make_readable`; `invoke_agent`/`invoke_agent_streaming` gain `run_as_user`, wrap the command, and chmod temp files 0o644 so the runuser child can read them |
| `backend/services/chat/chat_service.py` | resolves the run-as user via `get_platform_run_as_user` and threads it into both invoke paths |
| `backend/services/workspace/platform_user.py` | `get_platform_run_as_user(db)` — `worker_user` of the local platform server, or None |
| `tests/unit/test_agent_process_runuser.py` | `_wrap_runuser` no-op / wrap / quoting |

### SSH-to-host + run-as seeding (T2, opt-in scaffolding)
| File | Change |
|------|--------|
| `backend/config.py` | `platform_user`, `platform_ssh_host`, `platform_ssh_port`, `platform_workspace_root` (all empty by default) |
| `backend/seed/platform_server.py` | sets `worker_user` from `PLATFORM_USER`; when `PLATFORM_SSH_HOST` is set, seeds/switches the platform server to `server_type=remote`/host-gateway (idempotent); agent discovery via `executor_for_server` |
| `docker-compose.yml`, `docker-compose.dev.yml` | `extra_hosts: host-gateway:host-gateway` on backend |
| `claudedocs/runbooks/platform-host-execution.md` | one-time host setup (sshd, authorized_keys, root SSH) |

## Verification
- Backend import smoke OK; new unit tests pass; full suite green; ruff + pyright clean.
- 37 related (chat/seed/terminal/ws) tests pass.

## Deferred (follow-up)
- **tmux local-terminal sessions** (`local_terminals.py` create/resume + `ws.py:_attach_to_tmux`)
  with a `run_as_user` column + migration — more PTY/ownership complexity.
- **`LaunchAgentModal`** passing `worker_user` instead of hard-coded `"root"`.
- The **host-side setup** (WSL2 `sshd`, authorized_keys) is the operator's step per the runbook.

## Notes
- Activation is gated entirely on the platform server's `worker_user` (set via `PLATFORM_USER`)
  and `PLATFORM_SSH_HOST`. With both unset, every path falls through to the prior root behaviour.
- When run-as-user is active, the non-root user needs the agent CLIs + `GITHUB_TOKEN` in its
  login env, otherwise chat reports "agent not installed" — documented in the runbook.

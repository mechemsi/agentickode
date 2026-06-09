---
title: Enable platform host execution (SSH-to-host) + run-as user
---

# Platform host execution (SSH-to-host) + run-as user

By default the built-in **platform** workspace server runs commands *inside the backend
container as root*. This runbook turns on two opt-in behaviours:

- **Run-as user** (`PLATFORM_USER`): terminal, chat, and agent launches run as a chosen OS
  user via `runuser` instead of root. Works in-container — no host setup needed.
- **SSH-to-host** (`PLATFORM_SSH_HOST`): the platform server executes on the *real host*
  over SSH instead of inside the container. Needs host-side setup (below).

Both are **off by default** — unset config = current in-container root behaviour, no regression.

## When to use

- You want platform terminal/chat/agents to run as a non-root user → set `PLATFORM_USER`.
- You want the platform server to operate on the actual host machine (host Docker, host
  paths, host-installed tools) → also set `PLATFORM_SSH_HOST=host-gateway`.

## Steps

### A. Run-as user only (no host SSH)

1. Set in `.env`:
   ```
   PLATFORM_USER=youruser
   ```
2. Ensure that user exists in the **backend container** and has the agent CLIs + `GITHUB_TOKEN`
   in its login env (the agents install to root's home by default — a non-root user needs its
   own copy / PATH). For most setups, leave `PLATFORM_USER` unset and run as root.
3. Restart backend: `docker compose -f docker-compose.dev.yml up -d backend`.
4. The seed sets `worker_user` on the platform server; terminal/chat/agent now run via
   `runuser -l youruser`.

### B. SSH-to-host (true host execution)

1. **On the host**, ensure an SSH daemon is running and accepts the container's key:
   ```bash
   sudo systemctl enable --now ssh        # or: sudo service ssh start  (WSL2)
   # Add the backend container's public key to the host's authorized_keys:
   docker compose -f docker-compose.dev.yml exec backend cat /root/.ssh/id_ed25519.pub \
     >> ~/.ssh/authorized_keys
   ```
   The SSH user must be **root** (or have NOPASSWD sudo) so `runuser -l <user>` works.
2. Set in `.env`:
   ```
   PLATFORM_SSH_HOST=host-gateway
   PLATFORM_SSH_PORT=22
   PLATFORM_USER=youruser
   PLATFORM_WORKSPACE_ROOT=/home/youruser/agentickode-workspaces
   ```
3. Restart backend: `docker compose -f docker-compose.dev.yml up -d backend`.
4. The seed switches the platform server to `server_type=remote`, `hostname=host-gateway`.
   Verify from the UI (Workspace Servers → platform → Test Connection) or:
   ```bash
   docker compose -f docker-compose.dev.yml exec backend \
     ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@host-gateway 'whoami'
   ```

## Common Issues

| Symptom | Fix |
|---------|-----|
| `Permission denied (publickey)` to host-gateway | Container key not in host `~/.ssh/authorized_keys`; re-run step B.1. |
| `host-gateway: Name or service not known` | `extra_hosts: host-gateway:host-gateway` missing / WSL2 network mode; set `PLATFORM_SSH_HOST` to the host IP instead. |
| `runuser: user <x> does not exist` | The run-as user doesn't exist on the SSH target; create it or unset `PLATFORM_USER`. |
| Chat agent "not installed in this container" after setting `PLATFORM_USER` | The non-root user lacks the agent CLIs on its PATH; install them for that user or run as root. |
| Want to revert | Unset `PLATFORM_SSH_HOST`/`PLATFORM_USER` and restart; the platform server stays whatever it was last seeded as — manually set it back to `server_type=local` in the DB if needed. |

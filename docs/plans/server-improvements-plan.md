<!-- Copyright (c) 2026 Mechemsi. All rights reserved. -->
<!-- Licensed under AGPLv3. See LICENSE file. -->
<!-- Commercial licensing: info@mechemsi.com -->

# Server Improvements Plan

## Executive Summary

Five features to enhance workspace server management:

1. **Server Groups** — Group servers to share SSH keys and git tokens
2. **Shared Git Tokens** — One git token per group, deployed to all servers
3. **Redis Queue + Restart Recovery** — Persistent queue, per-server concurrency, orphan recovery
4. **Docker Management** — View/manage Docker containers on workspace servers via UI
5. **Terminal User Selection** — Choose root or worker user when opening terminal

## Feature 1: Server Groups with Shared SSH Keys

### Current State
- Each `WorkspaceServer` independently manages SSH keys
- `GitAccessService` generates/checks keys per-server
- No grouping concept exists

### Target State
- New `ServerGroup` model with name, description
- `WorkspaceServer` gets optional `server_group_id` FK
- Shared SSH key generated once, deployed to all group members
- Group-level git access check/generation endpoints

### Files to Create
- `backend/models/server_groups.py` — ServerGroup model
- `backend/schemas/server_groups.py` — CRUD schemas
- `backend/repositories/server_group_repo.py` — Repository
- `backend/api/servers/server_groups.py` — API endpoints
- `alembic/versions/xxx_add_server_groups.py` — Migration
- `frontend/src/components/servers/ServerGroupPanel.tsx` — Group management UI

### Files to Modify
- `backend/models/servers.py` — Add `server_group_id` FK to WorkspaceServer
- `backend/models/__init__.py` — Export ServerGroup
- `backend/schemas/servers.py` — Add `server_group_id` to create/update/out schemas
- `backend/api/servers/__init__.py` — Register server_groups router
- `frontend/src/api/servers.ts` — Add group API calls
- `frontend/src/types/index.ts` — Add ServerGroup type
- `frontend/src/pages/WorkspaceServers.tsx` — Show group assignment UI

### Implementation Steps
1. Create ServerGroup model with id, name, description, timestamps
2. Add server_group_id FK to WorkspaceServer (nullable)
3. Create Alembic migration
4. Create schemas and repository
5. Create CRUD API endpoints + deploy-key-to-group endpoint
6. Frontend: Group CRUD panel + assign servers to groups
7. Group-level git key generation: generate once, SSH-copy to all members

## Feature 2: Shared Git Token per Server Group

### Current State
- No git token management on workspace servers
- Each server needs manual `gh auth login` or token setup

### Target State
- `ServerGroup` has encrypted `git_token` and `git_provider` fields
- API to set/deploy token to all group servers via SSH
- Auto-deploy token when server joins group

### Implemented Within Feature 1
- `ServerGroup` model gets `git_token_encrypted`, `git_provider_type` fields
- `backend/services/workspace/group_token_service.py` — Deploy token to servers via SSH
- API endpoint: `POST /api/server-groups/{id}/deploy-token`
- Deploys `gh auth` or git credential-store config to all servers

## Feature 3: Redis Queue + Restart Recovery

### Current State
- WorkerEngine polls DB for pending tasks (`_dispatch_pending`)
- `max_concurrent_runs` is global (default: 3), not per-server
- Basic restart recovery exists: resets "running" to "pending"
- Redis is in docker-compose but unused by backend
- No per-server concurrency limits

### Target State
- Redis used for task queue with persistence (AOF)
- Per-server configurable `max_concurrent_tasks` (default: 1)
- Enhanced restart recovery with run state logging
- Queue state visible in API

### Files to Create
- `backend/services/queue_service.py` — Redis-backed queue service

### Files to Modify
- `backend/models/servers.py` — Add `max_concurrent_tasks` to WorkspaceServer
- `backend/schemas/servers.py` — Add `max_concurrent_tasks` to schemas
- `backend/config.py` — Add `redis_url` setting
- `backend/worker/engine.py` — Use Redis queue, per-server concurrency
- `backend/main.py` — Initialize Redis connection in lifespan

### Implementation Steps
1. Add `redis_url` to Settings and `max_concurrent_tasks` to WorkspaceServer
2. Create `QueueService` with Redis: enqueue, dequeue, ack, get_queue_status
3. Modify WorkerEngine._dispatch_pending to respect per-server limits
4. Enhanced _recover_interrupted_runs: log recovery, configurable behavior
5. API endpoint for queue status visibility
6. Migration for max_concurrent_tasks column

## Feature 4: Docker Management for Workspace Servers

### Current State
- Zero Docker management exists for remote workspace servers

### Target State
- Service to run Docker commands remotely via SSH
- API endpoints for container/image/volume/network management
- Frontend Docker tab in workspace server detail

### Files to Create
- `backend/services/workspace/docker_service.py` — Remote Docker operations via SSH
- `backend/api/servers/docker_management.py` — API endpoints
- `backend/schemas/docker.py` — Docker response schemas
- `frontend/src/components/servers/DockerPanel.tsx` — Docker management UI

### Files to Modify
- `backend/api/servers/__init__.py` — Register docker router
- `frontend/src/api/servers.ts` — Add Docker API calls
- `frontend/src/types/index.ts` — Add Docker types
- `frontend/src/pages/WorkspaceServers.tsx` — Add Docker tab button/panel

### Implementation Steps
1. Create DockerService with SSH-based Docker commands:
   - list_containers(all=True), list_images, list_volumes, list_networks
   - container_logs(id, tail), start/stop/restart_container
   - prune_containers, prune_images, prune_volumes, prune_all (system prune)
   - container_inspect, image_inspect
2. Create schemas for Docker responses
3. Create API endpoints under `/workspace-servers/{id}/docker/`
4. Frontend: DockerPanel with tabs for containers, images, volumes, networks
5. Prune controls with confirmation dialogs
6. Container action buttons (start/stop/restart/remove)

## Feature 5: Terminal User Selection

### Current State
- `ws_terminal` endpoint connects as server's configured `ssh_user` (root)
- No query param for user selection
- `ws_run_terminal` uses `runuser` for worker user but no choice
- Frontend `TerminalPanel` takes only `serverId`, no user param

### Target State
- Terminal WebSocket accepts `?user=root|worker` query param
- Frontend shows user selection dropdown before/when opening terminal
- Each option shows username and home directory

### Files to Modify
- `backend/api/ws.py` — Add `user` query param to `ws_terminal`
- `frontend/src/components/runs/TerminalPanel.tsx` — Accept `user` prop, pass in WS URL
- `frontend/src/pages/WorkspaceServers.tsx` — Show user selection dropdown for terminal

### Implementation Steps
1. Modify `ws_terminal` to accept `user` query param
2. If user=worker and worker_user configured, use `runuser -l {worker_user} -c bash`
3. Frontend: Add user selection state per server
4. Show dropdown with "root" and worker user (if configured) options
5. Pass selected user to TerminalPanel, which appends `?user=X` to WS URL

## Dependency Order

Features 1+2 are coupled (server groups + tokens). Features 3, 4, 5 are independent.
All can be developed in parallel.

```
Feature 1+2 (Server Groups)     ──┐
Feature 3   (Redis Queue)       ──┤── All parallel
Feature 4   (Docker Management) ──┤
Feature 5   (Terminal Selection) ─┘
```

## Complexity Estimates

| Feature | Backend | Frontend | Migration | Total |
|---------|---------|----------|-----------|-------|
| 1+2 Server Groups | High | Medium | Yes | High |
| 3 Redis Queue | High | Low | Yes | High |
| 4 Docker Mgmt | Medium | High | No | High |
| 5 Terminal User | Low | Low | No | Low |

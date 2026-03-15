# Git Connections Feature Design

## Problem
Git provider tokens (GitHub, Bitbucket, GitLab, Gitea) are only configurable via `.env` file — global for all servers and projects. Users need per-server and per-project token management through the UI, with encrypted storage and write-only access.

## Solution
A new `git_connections` table storing encrypted tokens with flexible scoping (global, per-server, per-project).

## Model

```
git_connections
├── id                   Integer PK
├── name                 Text (e.g. "GitHub - Company Org")
├── provider             Text (github/gitea/gitlab/bitbucket)
├── base_url             Text nullable (self-hosted URL)
├── token_enc            Text (Fernet encrypted)
├── scope                Text (global/server/project)
├── workspace_server_id  FK nullable → workspace_servers.id
├── project_id           FK nullable → project_configs.project_id
├── is_default           Boolean default false
├── created_at, updated_at
```

## Token Resolution Order
1. Project-scoped connection matching provider
2. Server-scoped connection matching provider
3. Global default matching provider
4. `.env` fallback

## API Endpoints
- `GET    /api/git-connections` — list (filter by scope/server_id/project_id)
- `POST   /api/git-connections` — create
- `PUT    /api/git-connections/{id}` — update
- `DELETE /api/git-connections/{id}` — delete
- `POST   /api/git-connections/{id}/test` — test connection

## Schema (write-only tokens)
- Input accepts plaintext token
- Output returns `has_token: bool`, never the value
- Stored encrypted via `encrypt_value()`

## Worker Integration
`WorkerUserService._build_env_vars()` and `_build_git_credentials()` accept optional connections, preferring DB over `.env`.

## Frontend
Git Tokens section in GitAccessPanel + standalone connections management.

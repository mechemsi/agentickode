---
title: Notion task source + issue polling fallback
status: implemented
date: 2026-05-02
related:
  - ../decisions/006-multi-source-task-intake.md
---

## What Was Built

Two related additions to task ingestion:

1. **Notion as a first-class task source** — webhook handler, scheduled poller, and bidirectional `TaskManager` (status updates, comments, page creation). Per-project Notion API key is stored encrypted on `project_configs.integration_config`.
2. **Issue polling as a webhooks fallback** — generic `IssuePoller` Protocol with implementations for GitHub, Gitea, GitLab, Plane, and Notion. A new `IssuePollerScheduler` ticks every 60s and dispatches per-project pulls based on `poll_enabled` and `poll_interval_minutes`.

This closes the gap where users behind firewalls or on trackers without webhook delivery had no way to get tasks into the platform.

## Key Files

| File | Purpose |
|------|---------|
| `alembic/versions/035_add_polling_and_integration_config.py` | Adds `poll_enabled`, `poll_interval_minutes`, `last_polled_at`, `next_poll_at`, `integration_config` to `project_configs` |
| `backend/services/task_source_polling/protocol.py` | `IssuePoller` Protocol — `poll(project, session) -> list[int]`, idempotent |
| `backend/services/task_source_polling/factory.py` | Maps `task_source` → poller |
| `backend/services/task_source_polling/_dedupe.py` | `existing_task_ids()` — shared dedupe lookup |
| `backend/services/task_source_polling/{github,gitea,gitlab,plane,notion}_poller.py` | Per-source pollers |
| `backend/worker/issue_poller_scheduler.py` | Tick loop, picks `poll_enabled` projects whose `next_poll_at` has elapsed |
| `backend/services/task_management/notion_manager.py` | Bidirectional Notion `TaskManager` (status, comments, page creation) |
| `backend/services/task_management/factory.py` | Resolves Notion API key from `project.integration_config` (encrypted or plaintext fallback) |
| `backend/api/webhooks.py` | Adds `POST /api/webhooks/notion` with subscription handshake, ai-task tag filter, dedupe |
| `backend/api/projects.py` | Encrypts secret keys in `integration_config`; redacts on output as `has_<key>` flags |
| `backend/services/task_source_updater.py` | Adds `_notify_notion()` for phase-transition comments |
| `frontend/src/components/shared/ProjectForm.tsx` | UI for polling toggle + Notion DB/key/property fields, with `data-testid="notion-fields"` and `polling-fields` |

## How It Works

### Polling tick
1. `IssuePollerScheduler.run()` sleeps `poll_seconds` (default 60) between ticks.
2. `_due_projects()` selects `ProjectConfig` rows where `poll_enabled=True` AND (`next_poll_at IS NULL OR next_poll_at <= now`).
3. Per project, `get_poller(task_source)` returns the right `IssuePoller` (or `None` for unsupported sources, in which case the scheduler still advances `next_poll_at` to avoid spinning).
4. The poller fetches open issues, filters by `ai-task` label/tag, dedupes via `existing_task_ids()`, and creates `TaskRun` rows through `create_task_run()`.
5. `_advance()` writes `last_polled_at = now` and `next_poll_at = now + poll_interval_minutes`.

A failing poller logs and is swallowed — one bad project does not stall the loop.

### Notion secret handling
- Frontend submits `integration_config.notion_api_key` as plaintext.
- `_encrypt_integration_secrets()` (in `backend/api/projects.py`) rewrites known secret keys (`notion_api_key`, `plane_api_key`) into `<key>_enc` Fernet ciphertexts before persistence.
- `_project_out()` strips both plaintext and `_enc` variants on the way out and adds `has_<key>: bool` flags.
- `update_project()` merges `integration_config` rather than replacing it, so a partial PATCH can change `notion_database_id` without wiping the stored key.

### Bidirectional sync
- The `StatusSyncer` listens to broadcaster events (`run_started`, `run_completed`, `run_failed`), looks up the run's project, and now passes the project to `get_task_manager(...)` so the Notion factory can resolve per-project credentials.
- `NotionTaskManager.update_status()` patches the page's Status select via the `notion_status_property` configured on the project.
- `TaskSourceUpdater._notify_notion()` posts per-phase comments using the same per-project key.

## Notes

- Notion subscription verification is handled in the webhook by echoing back `verification_token` when the body has no `event` or `page` field.
- The Notion poller skips pages whose Status is already `done` or `completed` to avoid resurrecting closed work.
- `_INTEGRATION_SECRET_KEYS = ("notion_api_key", "plane_api_key")` is the canonical list — add to it when introducing a new integration secret so encrypt + redact stay in sync.
- The migration uses `JSONB` with a `'{}'::jsonb` server default; the auto-migrator in `main.py` uses the same SQL for SQLite-backed dev but tests run on in-memory SQLite where JSONB → JSON via the conftest mapping.
- Tests covering the new paths: `tests/unit/test_{github,notion}_poller.py`, `test_issue_poller_scheduler.py`, `test_notion_manager.py`, `test_notion_webhook.py`, `test_task_source_updater.py` (Notion notify cases), `tests/integration/test_projects_api.py` (`TestProjectsIntegrationConfig`).

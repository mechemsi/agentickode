# Split Large Files Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split 6 files exceeding 400-line limit into smaller, SOLID-compliant modules.

**Architecture:** Each large file is split by concern (prompts/templates, execution modes, utilities). Backward-compatible re-exports preserve existing imports. Tests patches updated to new module paths.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest

---

## Task 1: Split `coding.py` (1028 lines → 4 files)

**Split strategy:**
- `coding.py` — main `run()` orchestrator + constants (~280 lines)
- `_coding_consolidated.py` — `_run_consolidated()` (~200 lines)
- `_coding_batch.py` — `_run_batch()` + `_build_batch_prompt()` (~200 lines)
- `_coding_utils.py` — prompts, templates, git helpers (~180 lines)

**Files:**
- Create: `backend/worker/phases/_coding_consolidated.py`
- Create: `backend/worker/phases/_coding_batch.py`
- Create: `backend/worker/phases/_coding_utils.py`
- Modify: `backend/worker/phases/coding.py`
- Modify: `backend/worker/phases/_comparison.py` (imports)
- Modify: `tests/unit/test_coding.py` (patches)
- Modify: `tests/unit/test_coding_session.py` (patches)

**What goes where:**

`_coding_utils.py`:
- All template constants (FALLBACK_SYSTEM_PROMPT, FALLBACK_USER_TEMPLATE, CONTINUATION_TEMPLATE, BATCH_TEMPLATE, CONSOLIDATED_TEMPLATE)
- `_build_coding_prompt()`, `_build_continuation_prompt()`, `_build_batch_prompt()`
- `_auto_commit_changes()`, `_get_previous_session_id()`, `_make_results()`, `_format_pr_comments()`

`_coding_batch.py`:
- `_run_batch()` — imports templates + utils from `_coding_utils`

`_coding_consolidated.py`:
- `_run_consolidated()` — imports templates + utils from `_coding_utils`

`coding.py`:
- `run()` + `PHASE_META` — imports from all three submodules
- Re-export `FALLBACK_SYSTEM_PROMPT`, `FALLBACK_USER_TEMPLATE`, `_build_coding_prompt` for `_comparison.py`

## Task 2: Split `reviewing.py` (410 lines → 2 files)

**Split strategy:**
- `reviewing.py` — main `run()` + setup + constants (~200 lines)
- `_reviewing_loop.py` — retry loop + iteration logic + `_get_diff()` (~210 lines)

**Files:**
- Create: `backend/worker/phases/_reviewing_loop.py`
- Modify: `backend/worker/phases/reviewing.py`
- Modify: `tests/unit/test_reviewing.py` (patches)

## Task 3: Split `workspace_servers.py` (478 lines → 3 files)

**Split strategy:**
- `workspace_servers.py` — CRUD + serialization + router (~200 lines)
- `workspace_servers_discovery.py` — `deploy_key_to_server()`, `scan_workspace_server()` (~180 lines)
- `workspace_servers_ops.py` — `test_workspace_server()`, setup/log/retry, invocations (~120 lines)

All three have their own `APIRouter` with tag. Main `__init__.py` mounts all.

**Files:**
- Create: `backend/api/servers/workspace_servers_discovery.py`
- Create: `backend/api/servers/workspace_servers_ops.py`
- Modify: `backend/api/servers/workspace_servers.py`
- Modify: `backend/api/servers/__init__.py` (mount new routers)
- Modify: `backend/main.py` (include new routers)

## Task 4: Split `runs.py` (462 lines → 3 files)

**Split strategy:**
- `runs.py` — CRUD (list, create, get, stats) + router (~130 lines)
- `runs_actions.py` — state transitions (approve, reject, retry, restart, cancel, terminal) (~200 lines)
- `runs_phases.py` — phase management + invocations + comparison (~150 lines)

**Files:**
- Create: `backend/api/runs_actions.py`
- Create: `backend/api/runs_phases.py`
- Modify: `backend/api/runs.py`
- Modify: `backend/main.py` (include new routers)

## Task 5: Split `cli_adapter.py` (420 lines → 2 files)

**Split strategy:**
- `cli_adapter.py` — `CLIAdapter` class with init, properties, `_run_ssh`, `generate()`, `is_available()` (~230 lines)
- `_cli_task_runner.py` — `run_task()`, `_detect_changed_files()`, `close_session()` as mixin or extracted functions (~190 lines)

Actually better: keep as one class but extract into two files using a mixin pattern.

**Files:**
- Create: `backend/services/adapters/_cli_task_mixin.py`
- Modify: `backend/services/adapters/cli_adapter.py`

## Task 6: Split `setup_service.py` (407 lines → 2 files)

**Split strategy:**
- `setup_service.py` — `ServerSetupService` class + orchestration (~200 lines)
- `_setup_steps.py` — step handlers + dependency installation (~210 lines)

**Files:**
- Create: `backend/services/workspace/_setup_steps.py`
- Modify: `backend/services/workspace/setup_service.py`
- Modify: `backend/services/workspace/__init__.py` (update imports)

---

## Verification

After each task:
```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/ tests/
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -x -v
```

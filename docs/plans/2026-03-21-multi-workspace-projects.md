# Multi-Workspace Projects Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow a project to be assigned to multiple workspace servers and run non-conflicting tasks in parallel across them.

**Architecture:** Replace `ProjectConfig.workspace_server_id` (singular FK) with an M:N join table `project_workspace_servers`. Add `workspace_server_id` to `TaskRun` so each run tracks which workspace it used. Relax the engine's "one active run per project" lock to "one active run per project+workspace". Give each task its own isolated workspace path to prevent git index races.

**Tech Stack:** SQLAlchemy async, Alembic, FastAPI, React/TypeScript, APScheduler (engine loop)

---

## Task 1: Database Migration

**Files:**
- Create: `alembic/versions/024_multi_workspace_projects.py`

**Step 1: Create migration file**

```python
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""multi-workspace projects

Revision ID: 024
Revises: 023
Create Date: 2026-03-21

"""

from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # M:N join table for project <-> workspace server assignments
    op.create_table(
        "project_workspace_servers",
        sa.Column("project_id", sa.Text(), sa.ForeignKey("project_configs.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_server_id", sa.Integer(), sa.ForeignKey("workspace_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("project_id", "workspace_server_id"),
    )
    op.create_index("ix_pws_project_id", "project_workspace_servers", ["project_id"])
    op.create_index("ix_pws_server_id", "project_workspace_servers", ["workspace_server_id"])

    # Migrate existing singular workspace assignment to join table
    op.execute("""
        INSERT INTO project_workspace_servers (project_id, workspace_server_id, priority)
        SELECT project_id, workspace_server_id, 0
        FROM project_configs
        WHERE workspace_server_id IS NOT NULL
    """)

    # Add workspace_server_id to task_runs (which workspace executed this run)
    op.add_column("task_runs", sa.Column("workspace_server_id", sa.Integer(), sa.ForeignKey("workspace_servers.id", ondelete="SET NULL"), nullable=True))

    # Backfill task_runs.workspace_server_id from project's former single workspace
    op.execute("""
        UPDATE task_runs tr
        SET workspace_server_id = pc.workspace_server_id
        FROM project_configs pc
        WHERE tr.project_id = pc.project_id
          AND pc.workspace_server_id IS NOT NULL
          AND tr.workspace_server_id IS NULL
    """)

    # Drop old singular FK column from project_configs
    op.drop_column("project_configs", "workspace_server_id")


def downgrade() -> None:
    op.add_column("project_configs", sa.Column("workspace_server_id", sa.Integer(), sa.ForeignKey("workspace_servers.id", ondelete="SET NULL"), nullable=True))
    op.execute("""
        UPDATE project_configs pc
        SET workspace_server_id = pws.workspace_server_id
        FROM project_workspace_servers pws
        WHERE pc.project_id = pws.project_id
    """)
    op.drop_column("task_runs", "workspace_server_id")
    op.drop_index("ix_pws_server_id", "project_workspace_servers")
    op.drop_index("ix_pws_project_id", "project_workspace_servers")
    op.drop_table("project_workspace_servers")
```

**Step 2: Apply migration**

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

Expected: `Running upgrade 023 -> 024, multi-workspace projects`

**Step 3: Commit**

```bash
git add alembic/versions/024_multi_workspace_projects.py
git commit -m "feat: add multi-workspace migration (project_workspace_servers join table)"
```

---

## Task 2: SQLAlchemy Model — ProjectWorkspaceServer join model + update ProjectConfig

**Files:**
- Modify: `backend/models/projects.py`
- Modify: `backend/models/__init__.py`

**Step 1: Add ProjectWorkspaceServer model and update ProjectConfig**

In `backend/models/projects.py`, add the new join model and update `ProjectConfig`:

- Add `ProjectWorkspaceServer` model (columns: `project_id`, `workspace_server_id`, `priority`, `created_at`)
- Change `ProjectConfig.workspace_server_id` singular FK to `workspace_servers` relationship via `ProjectWorkspaceServer`
- Add `workspace_server_id` to `TaskRun` in `backend/models/runs.py`

**Step 2: Run type check on edited files**

```bash
docker compose -f docker-compose.dev.yml exec backend pyright backend/models/projects.py backend/models/runs.py
```

Expected: no errors

**Step 3: Run model tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_models.py -x -v
```

Expected: all pass

**Step 4: Commit**

```bash
git add backend/models/projects.py backend/models/runs.py backend/models/__init__.py
git commit -m "feat: add ProjectWorkspaceServer model, update ProjectConfig and TaskRun"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Modify: `backend/schemas/projects.py`

**Step 1: Update schemas**

In `backend/schemas/projects.py`:
- Remove `workspace_server_id: int | None` from `ProjectConfigCreate` / `ProjectConfigUpdate` / `ProjectConfigOut`
- Add `workspace_server_ids: list[int]` to `ProjectConfigCreate` (required, min 1)
- Add `workspace_server_ids: list[int] = []` to `ProjectConfigUpdate`
- Add `workspace_server_ids: list[int]` to `ProjectConfigOut`

**Step 2: Run type check**

```bash
docker compose -f docker-compose.dev.yml exec backend pyright backend/schemas/projects.py
```

Expected: no errors

**Step 3: Commit**

```bash
git add backend/schemas/projects.py
git commit -m "feat: update project schemas to use workspace_server_ids list"
```

---

## Task 4: Repository Layer

**Files:**
- Modify: `backend/repositories/project_config_repo.py`

**Step 1: Write failing tests**

In `tests/unit/test_project_config_repo.py`, add tests:

```python
async def test_create_project_with_multiple_workspaces(session, make_workspace_server):
    ws1 = await make_workspace_server()
    ws2 = await make_workspace_server()
    repo = ProjectConfigRepository(session)
    project = await repo.create({"project_id": "test", ..., "workspace_server_ids": [ws1.id, ws2.id]})
    assert len(project.workspace_servers) == 2

async def test_update_project_workspace_servers(session, make_project_config, make_workspace_server):
    ws1 = await make_workspace_server()
    ws2 = await make_workspace_server()
    project = await make_project_config(workspace_server_ids=[ws1.id])
    repo = ProjectConfigRepository(session)
    await repo.update(project.project_id, {"workspace_server_ids": [ws2.id]})
    updated = await repo.get(project.project_id)
    server_ids = [pws.workspace_server_id for pws in updated.workspace_servers]
    assert server_ids == [ws2.id]
```

**Step 2: Run to verify they fail**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_project_config_repo.py::test_create_project_with_multiple_workspaces -x -v
```

Expected: FAIL

**Step 3: Implement in repository**

In `ProjectConfigRepository.create()`:
- After creating `ProjectConfig`, insert `ProjectWorkspaceServer` rows for each `workspace_server_id` in `data["workspace_server_ids"]`

In `ProjectConfigRepository.update()`:
- If `workspace_server_ids` in patch: delete existing `ProjectWorkspaceServer` rows, insert new ones

**Step 4: Run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_project_config_repo.py -x -v
```

Expected: all pass

**Step 5: Commit**

```bash
git add backend/repositories/project_config_repo.py tests/unit/test_project_config_repo.py
git commit -m "feat: repository supports workspace_server_ids list for create/update"
```

---

## Task 5: API Layer — Projects endpoint

**Files:**
- Modify: `backend/api/projects.py`

**Step 1: Update route handlers**

- `POST /api/projects`: Accept `workspace_server_ids: list[int]` instead of `workspace_server_id: int | None`
- `PATCH /api/projects/{id}`: Accept `workspace_server_ids: list[int] | None = None`
- `GET /api/projects/{id}` response: Include `workspace_server_ids` list

**Step 2: Run lint and type check**

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/api/projects.py --fix
docker compose -f docker-compose.dev.yml exec backend pyright backend/api/projects.py
```

**Step 3: Run integration tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/integration/test_projects_api.py -x -v
```

**Step 4: Commit**

```bash
git add backend/api/projects.py
git commit -m "feat: projects API accepts workspace_server_ids list"
```

---

## Task 6: Workspace Assignment Strategy

**Files:**
- Create: `backend/services/workspace/workspace_selector.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_workspace_selector.py

async def test_selects_least_loaded_server(session, make_project_config, make_task_run):
    """Picks workspace with fewest active runs"""
    # project has ws1 (2 active runs) and ws2 (0 active runs)
    # expect ws2 to be selected

async def test_returns_none_when_no_servers_assigned(session, make_project_config):
    """Returns None if project has no workspace servers"""

async def test_respects_priority_order_when_equal_load(session, make_project_config):
    """With equal load, picks lowest priority value (0 = highest priority)"""
```

**Step 2: Run to verify they fail**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_workspace_selector.py -x -v
```

**Step 3: Implement workspace_selector.py**

```python
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Workspace server selection strategy for multi-workspace projects."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ProjectWorkspaceServer, TaskRun


async def select_workspace_for_run(
    project_id: str,
    session: AsyncSession,
    *,
    exclude_server_ids: list[int] | None = None,
) -> int | None:
    """Return workspace_server_id with fewest active runs for the project.

    Returns None if the project has no assigned workspace servers.
    """
    exclude = set(exclude_server_ids or [])

    # Count active runs per server for this project
    active_counts = (
        select(
            TaskRun.workspace_server_id,
            func.count(TaskRun.id).label("active"),
        )
        .where(
            TaskRun.project_id == project_id,
            TaskRun.status.in_(["pending", "running"]),
            TaskRun.workspace_server_id.isnot(None),
        )
        .group_by(TaskRun.workspace_server_id)
        .subquery()
    )

    # Join with project's assigned servers, ordered by load then priority
    row = await session.execute(
        select(
            ProjectWorkspaceServer.workspace_server_id,
        )
        .outerjoin(
            active_counts,
            ProjectWorkspaceServer.workspace_server_id == active_counts.c.workspace_server_id,
        )
        .where(ProjectWorkspaceServer.project_id == project_id)
        .where(
            ProjectWorkspaceServer.workspace_server_id.not_in(exclude)
            if exclude else True
        )
        .order_by(
            func.coalesce(active_counts.c.active, 0).asc(),
            ProjectWorkspaceServer.priority.asc(),
        )
        .limit(1)
    )
    result = row.scalar_one_or_none()
    return result
```

**Step 4: Run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_workspace_selector.py -x -v
```

Expected: all pass

**Step 5: Commit**

```bash
git add backend/services/workspace/workspace_selector.py tests/unit/test_workspace_selector.py
git commit -m "feat: workspace selector picks least-loaded server for project"
```

---

## Task 7: TaskRun Creation — Assign Workspace at Dispatch Time

**Files:**
- Modify: `backend/api/runs.py` (or wherever TaskRun is created — check `POST /api/runs`)
- Modify: `backend/worker/engine.py`

**Step 1: Update run creation**

When `POST /api/runs` creates a TaskRun:
- If `workspace_server_id` provided in request body: use it directly
- Otherwise: call `select_workspace_for_run(project_id, session)` and store result in `task_run.workspace_server_id`

**Step 2: Update engine dispatch constraint**

In `backend/worker/engine.py`, the current guard is:
```python
# Current — blocks all parallel runs for same project
if task_run.project_id in self._dispatched_projects:
    continue
```

Change to track `(project_id, workspace_server_id)` pairs:
```python
# New — allows parallel runs on different workspaces
dispatch_key = (task_run.project_id, task_run.workspace_server_id)
if dispatch_key in self._dispatched_workspaces:
    continue
```

And update `_dispatched_workspaces: set[tuple[str, int | None]]` accordingly (add on dispatch, remove on completion).

**Step 3: Write tests**

```python
# tests/unit/test_engine.py
async def test_parallel_runs_on_different_workspaces_both_dispatch(engine, make_task_run):
    """Two pending runs for same project on different workspaces should both dispatch"""

async def test_same_workspace_blocks_second_run(engine, make_task_run):
    """Two pending runs for same project on same workspace should only dispatch one"""
```

**Step 4: Run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_engine.py -x -v
```

**Step 5: Commit**

```bash
git add backend/worker/engine.py backend/api/runs.py tests/unit/test_engine.py
git commit -m "feat: engine allows parallel runs per project on different workspaces"
```

---

## Task 8: Per-Task Workspace Path Isolation

**Files:**
- Modify: `backend/worker/phases/workspace_setup.py`

**Problem:** `workspace_path` is currently shared (`/home/worker/workspaces/repo-name`). Concurrent tasks on the same server would conflict on `.git/index.lock`.

**Step 1: Update workspace_setup to use task-scoped path**

Change workspace path to include `task_run.id`:
```
/home/worker/workspaces/{repo_name}/{task_run.id}/
```

Update `task_run.workspace_path` to this new isolated path.

The git clone/pull logic already creates the directory — it will now create a fresh clone per task. This is safe: each task gets its own git working tree. Cost: extra clone per task. Benefit: zero race conditions.

**Step 2: Update workspace cleanup in finalization**

In `backend/worker/phases/finalization.py`, after a run completes:
- Delete the task-scoped workspace directory: `rm -rf {workspace_path}`

**Step 3: Write test**

```python
# tests/unit/test_workspace_setup.py
async def test_workspace_path_is_task_scoped(make_task_run, mock_ssh):
    """workspace_path includes task_run.id to prevent concurrent clashes"""
    task_run = make_task_run(id=42)
    # after workspace_setup runs, workspace_path should contain "42"
    assert "42" in task_run.workspace_path
```

**Step 4: Run test**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_workspace_setup.py -x -v
```

**Step 5: Commit**

```bash
git add backend/worker/phases/workspace_setup.py backend/worker/phases/finalization.py tests/unit/test_workspace_setup.py
git commit -m "feat: task-scoped workspace paths prevent git index race conditions"
```

---

## Task 9: Helper — get_ssh_for_run uses TaskRun.workspace_server_id

**Files:**
- Modify: `backend/worker/phases/_helpers.py`

**Step 1: Update `get_ssh_for_run`**

Current: reads workspace server from `task_run.workspace_config` or falls back to project's single server.

New: read `task_run.workspace_server_id` directly (set at dispatch time in Task 7). Fall back to loading the project's first assigned server if `workspace_server_id` is None (backwards compat for old runs).

**Step 2: Run lint**

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/worker/phases/_helpers.py --fix
docker compose -f docker-compose.dev.yml exec backend pyright backend/worker/phases/_helpers.py
```

**Step 3: Commit**

```bash
git add backend/worker/phases/_helpers.py
git commit -m "fix: _helpers reads workspace_server_id from TaskRun directly"
```

---

## Task 10: Frontend — ProjectForm multi-select workspace servers

**Files:**
- Modify: `frontend/src/components/shared/ProjectForm.tsx`
- Modify: `frontend/src/types/projects.ts` (add `workspace_server_ids: number[]` to `ProjectConfig`)

**Step 1: Update TypeScript types**

In `frontend/src/types/projects.ts`:
- Change `workspace_server_id: number | null` → `workspace_server_ids: number[]`

**Step 2: Update ProjectForm**

Replace the single workspace server `<select>` with a multi-select or checkbox list:

```tsx
{/* Workspace Servers — multi-select */}
<div>
  <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wide">
    Workspace Servers
  </label>
  <div className="space-y-1 max-h-40 overflow-y-auto">
    {servers.map((s) => (
      <label key={s.id} className="flex items-center gap-2 cursor-pointer py-1">
        <input
          type="checkbox"
          checked={(formData.workspace_server_ids ?? []).includes(s.id)}
          onChange={(e) => {
            const ids = formData.workspace_server_ids ?? [];
            setFormData({
              ...formData,
              workspace_server_ids: e.target.checked
                ? [...ids, s.id]
                : ids.filter((id) => id !== s.id),
            });
          }}
          className="accent-blue-500"
        />
        <span className="text-sm text-gray-300">{s.name}</span>
        <span className="text-xs text-gray-600">{s.host}</span>
      </label>
    ))}
  </div>
</div>
```

**Step 3: Run lint**

```bash
docker compose -f docker-compose.dev.yml exec frontend npx eslint src/components/shared/ProjectForm.tsx --fix
```

**Step 4: Run frontend tests**

```bash
docker compose -f docker-compose.dev.yml exec frontend npx vitest run src/__tests__/ProjectForm.test.tsx
```

**Step 5: Commit**

```bash
git add frontend/src/components/shared/ProjectForm.tsx frontend/src/types/projects.ts
git commit -m "feat: ProjectForm uses multi-select workspace servers"
```

---

## Task 11: Frontend — NewRun workspace selector

**Files:**
- Modify: `frontend/src/pages/NewRun.tsx`

**Step 1: Add workspace dropdown when project has multiple servers**

In `NewRun.tsx`, after selecting a project:
- If `project.workspace_server_ids.length > 1`: show a `<select>` for workspace server choice
- If `project.workspace_server_ids.length === 1`: auto-select, no UI
- Pass `workspace_server_id` in the run creation payload

```tsx
{selectedProject && selectedProject.workspace_server_ids.length > 1 && (
  <div>
    <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wide">
      Workspace Server
    </label>
    <select
      value={workspaceServerId ?? ""}
      onChange={(e) => setWorkspaceServerId(Number(e.target.value) || null)}
      className="w-full bg-gray-800/60 border border-gray-700/50 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
    >
      <option value="">Auto-select (least loaded)</option>
      {servers
        .filter((s) => selectedProject.workspace_server_ids.includes(s.id))
        .map((s) => (
          <option key={s.id} value={s.id}>{s.name} — {s.host}</option>
        ))}
    </select>
  </div>
)}
```

**Step 2: Run lint**

```bash
docker compose -f docker-compose.dev.yml exec frontend npx eslint src/pages/NewRun.tsx --fix
```

**Step 3: Commit**

```bash
git add frontend/src/pages/NewRun.tsx
git commit -m "feat: NewRun shows workspace selector when project has multiple servers"
```

---

## Task 12: Projects page — show workspace server count

**Files:**
- Modify: `frontend/src/pages/Projects.tsx`

**Step 1: Update display**

Change the project row metadata display from:
```tsx
{p.repo_owner}/{p.repo_name} · {p.task_source}/{p.git_provider}
```

To also show workspace count:
```tsx
{p.repo_owner}/{p.repo_name} · {p.task_source}/{p.git_provider} · {p.workspace_server_ids.length} workspace{p.workspace_server_ids.length !== 1 ? "s" : ""}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/Projects.tsx
git commit -m "feat: projects list shows workspace server count"
```

---

## Task 13: API — runs endpoint accepts workspace_server_id

**Files:**
- Modify: `backend/schemas/runs.py` (or wherever TaskRun create schema is)

**Step 1: Add workspace_server_id to run creation schema**

```python
class TaskRunCreate(BaseModel):
    ...
    workspace_server_id: int | None = None  # None = auto-select
```

**Step 2: In POST /api/runs handler:**

```python
ws_id = body.workspace_server_id
if ws_id is None:
    ws_id = await select_workspace_for_run(project.project_id, session)
task_run.workspace_server_id = ws_id
```

**Step 3: Run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/integration/test_runs_api.py -x -v
```

**Step 4: Commit**

```bash
git add backend/schemas/runs.py backend/api/runs.py
git commit -m "feat: run creation accepts optional workspace_server_id with auto-select fallback"
```

---

## Task 14: Full Test Suite & Final Verification

**Step 1: Run full backend test suite**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -x -v
```

Expected: all pass

**Step 2: Run full frontend test suite**

```bash
docker compose -f docker-compose.dev.yml exec frontend npm test
```

Expected: all pass

**Step 3: Run lint and type check**

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/ --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/ tests/
docker compose -f docker-compose.dev.yml exec backend pyright backend/
docker compose -f docker-compose.dev.yml exec frontend npm run lint
```

**Step 4: Manual smoke test**

1. Open Projects page → create a new project with 2 workspace servers selected
2. Verify both servers appear in the DB join table: `SELECT * FROM project_workspace_servers WHERE project_id = '...'`
3. Create two task runs for the project → both should dispatch immediately (different workspaces)
4. Verify each `TaskRun.workspace_server_id` is set and different
5. Verify workspace paths are different and task-scoped: `/home/worker/workspaces/repo/{task_id}/`

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat: multi-workspace projects — parallel task execution across workspace servers"
```

---

## Migration Notes

- **Existing single-workspace projects**: The migration backfills `project_workspace_servers` from the old `workspace_server_id` column. Existing runs are backfilled with their project's former workspace. Zero data loss.
- **Engine dispatch key change**: `_dispatched_projects: set[str]` → `_dispatched_workspaces: set[tuple[str, int | None]]`. This is additive — old behavior for `None` workspace is preserved.
- **Workspace path change**: Old shared paths (`/workspaces/repo-name`) no longer used for new runs. Old runs in DB still reference their old paths (fine — they're complete).

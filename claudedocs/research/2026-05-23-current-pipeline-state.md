---
title: Current Pipeline State Snapshot (pre-overhaul reference)
status: snapshot
date: 2026-05-23
related:
  - ../plans/2026-05-23-agentic-workflow-overhaul.md
---

## Purpose

This is a **frozen reference snapshot** of the worker pipeline, workflow templates, inter-phase data contracts, and trigger entry points as they exist on the `main` branch on 2026-05-23. The agentic workflow overhaul plan (Phases 1–5) and follow-up work cite this file instead of re-investigating the codebase.

**Reading rule:** every claim below cites `file:line`. If the cited line no longer matches reality, the reader should update *this* doc, not derive a different understanding silently.

**Scope:** structural snapshot only — what exists, where, and how the pieces talk to each other. Decisions about what to keep, deprecate, or replace live in the plan and in ADR-007.

---

## 1. Hardcoded phase-name lists

The string list of phases lives in many places. The overhaul plan needs every site so we know what to update (or what to break) when we move to composable steps.

| # | File | Lines | What it is |
|---|------|-------|------------|
| 1 | `backend/worker/pipeline.py` | 30–39 | `PHASE_NAMES` — canonical fallback list of the 8 structured phases |
| 2 | `backend/worker/pipeline.py` | 44–48 | `_AUTONOMOUS_PHASE_SEQUENCES` — 3 alternate sequences (`autonomous`, `hybrid`, `multi_agent`) that bypass workflow templates |
| 3 | `backend/worker/pipeline.py` | 62–68 | `_LEGACY_RESULT_MAP` — phase name → `TaskRun` JSONB column (back-compat mirror) |
| 4 | `backend/worker/phases/registry.py` | 26–28 | `_NAME_OVERRIDES = {"init_phase": "init"}` — module-name-to-phase-name shim |
| 5 | `backend/seed/workflow_templates.py` | 35–end | 6 seeded templates (`default`, `planner`, `hotfix`, `small-task`, `pr-review`, `fix-pr`) each declaring phase strings |
| 6 | `backend/api/ws_office.py` | 22–32 | `_PHASE_ACTIVITY` — phase name → "office" activity string for the live UI |
| 7 | `tests/unit/test_pipeline.py` | 13–24 | `_ALL_PHASE_NAMES` — test fixture covering all phase modules (includes `pr_fetch`, `task_creation`) |
| 8 | `frontend/src/components/runs/PhaseTimeline.tsx` | 24–32 | `PHASES` array used to render the timeline (notice: no `testing`) |
| 9 | `frontend/src/components/runs/PhaseTimeline.tsx` | 34–42 | `phaseIcons` map (lucide icon per phase) |
| 10 | `frontend/src/pages/NewRun.tsx` | 19–26 | `PHASES_WITH_AGENTS` — drives the per-phase agent selector. **Missing `testing` and `approval`** — pre-existing inconsistency, not yet a bug report |
| 11 | `frontend/src/pages/RunDetail.tsx` | 326, 338 | Special-case branches: `phaseName === "coding"` and `phaseName === "reviewing"` — distinct result renderers per phase |
| 12 | `frontend/src/pages/WorkflowTemplates.tsx` | 163 | `isCodingPhase = phase.phase_name === "coding"` — gates the "execution mode" selector to coding-only |

**Authoritative source of truth at runtime:** `discover_phases()` in `backend/worker/phases/registry.py:45–83` walks `backend/worker/phases/` for modules with a `run()` callable and emits a `{phase_name: PhaseInfo}` dict. The hardcoded lists above are everywhere the registry is *not* consulted.

---

## 2. `PhaseConfig` schema (verbatim)

From `backend/schemas/workflows.py:16–28`:

```python
class PhaseConfig(BaseModel):
    phase_name: str
    enabled: bool = True
    role: str | None = None
    uses_agent: bool | None = None
    agent_mode: str | None = None
    timeout_seconds: int | None = None
    trigger_mode: str = "auto"
    notify_source: bool = False
    params: dict[str, Any] = {}
    cli_flags: dict[str, str] | None = None
    environment_vars: dict[str, str] | None = None
    command_templates: dict[str, str] | None = None
```

Companion model `LabelRule` (`backend/schemas/workflows.py:11–13`):

```python
class LabelRule(BaseModel):
    match_all: list[str] = []
    match_any: list[str] = []
```

CRUD wrappers (`backend/schemas/workflows.py:31–58`) just compose these into `WorkflowTemplateCreate`, `WorkflowTemplateUpdate`, `WorkflowTemplateOut`.

**Notes on current shape:**
- `phase_name` is a free string — there is no enum or registry validation at schema-construction time. The pipeline resolves the name against `discover_phases()` at execution time and silently `skipped`s unknown phases (`backend/worker/pipeline.py:242–246`).
- `trigger_mode` is a string, not a literal type. Real values used in the codebase: `"auto"`, `"wait_for_trigger"`, `"wait_for_approval"` (see `backend/worker/pipeline.py:256, 378`).
- `params`, `cli_flags`, `environment_vars`, `command_templates` are all freeform `dict`s. There's no validation that, e.g., a `coding` phase's `params.consolidated` is a bool — `_skip_phases_for_consolidated` at `backend/worker/pipeline.py:156–217` does its own ad-hoc resolution.
- There is no `delay_seconds` field on `PhaseConfig`, yet `backend/worker/pipeline.py:394` reads `phase_exec.phase_config.get("delay_seconds", settings.phase_delay_seconds)`. The pipeline accepts an extra-not-in-schema key because `PhaseExecution.phase_config` is a raw JSONB column.

---

## 3. `WorkflowTemplate` model (verbatim)

From `backend/models/workflows.py:12–25`:

```python
class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, unique=True, nullable=False)
    description = Column(Text, nullable=False, default="")
    label_rules = Column(JSONB, nullable=False, default=list)
    phases = Column(JSONB, nullable=False, default=list)
    is_default = Column(Boolean, nullable=False, default=False)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
```

**Key shape notes:**
- Both `label_rules` and `phases` are raw `JSONB` arrays. The schema (`PhaseConfig`, `LabelRule`) is only enforced at the FastAPI boundary, not at the DB layer.
- There is no `triggers` column today — webhooks/pollers/cron are independent systems that funnel into `TaskRun` rows tagged with `task_source` and `task_source_meta.labels`, and the label-match cascade then picks a template. Adding first-class `triggers` is Phase 2 of the overhaul.
- `is_system = True` is used by seeds to mark templates the platform owns (see all 6 seeded templates in `backend/seed/workflow_templates.py`).

---

## 4. `label_rules` shape and `match_labels` function (verbatim)

### Shape

`label_rules` is `list[LabelRule]` serialized as JSONB. Each `LabelRule`:

```python
class LabelRule(BaseModel):
    match_all: list[str] = []
    match_any: list[str] = []
```

A template matches a given `labels: list[str]` if **at least one** rule matches. A rule matches if `all(match_all) AND any(match_any)` against the label set. Empty `match_all` defaults to `True`; empty `match_any` defaults to `True`. Empty `label_rules` never matches via the label path — only via `is_default = True`.

### Seeded examples

From `backend/seed/workflow_templates.py:35–end`:

```python
{"name": "default",     "label_rules": []},
{"name": "planner",     "label_rules": [{"match_all": [], "match_any": ["plan-only", "decompose"]}]},
{"name": "hotfix",      "label_rules": [{"match_all": [], "match_any": ["hotfix", "quick-fix"]}]},
{"name": "small-task",  "label_rules": [{"match_all": [], "match_any": ["subtask"]}]},
# "pr-review" and "fix-pr" follow (see file)
```

The `match_any` lists carry the OR vocabulary; `match_all` is currently unused by all seeded templates.

### `match_labels` implementation (verbatim)

From `backend/repositories/workflow_template_repo.py:57–88`:

```python
async def match_labels(self, labels: list[str]) -> WorkflowTemplate | None:
    """Find the first non-default template whose label_rules match the given labels."""
    result = await self._session.execute(
        select(WorkflowTemplate)
        .where(WorkflowTemplate.is_default.is_(False))
        .order_by(WorkflowTemplate.name)
    )
    templates = result.scalars().all()
    label_set = set(labels)

    for template in templates:
        rules = template.label_rules or []
        if not rules:
            continue
        if self._rules_match(rules, label_set):
            return template

    return await self.get_default()

@staticmethod
def _rules_match(rules: list[dict], label_set: set[str]) -> bool:
    """Evaluate label rules: at least one rule must match."""
    for rule in rules:
        match_all = rule.get("match_all", [])
        match_any = rule.get("match_any", [])

        all_ok = all(lbl in label_set for lbl in match_all) if match_all else True
        any_ok = any(lbl in label_set for lbl in match_any) if match_any else True

        if all_ok and any_ok:
            return True
    return False
```

**Tie-breaking:** alphabetical by `name` (`ORDER BY name`). There is no priority field. If two non-default templates both match, the alphabetically-first one wins.

**Fallback:** if no non-default template matches, `get_default()` returns the template where `is_default = True` (or `None` if no default exists — at which point the pipeline falls back to `PHASE_NAMES` per `backend/worker/pipeline.py:142`).

---

## 5. Inter-phase data contracts

Phases communicate through two channels on the `TaskRun` row:

1. **Per-phase `PhaseExecution.result`** (JSONB) — written by the pipeline at `backend/worker/pipeline.py:347` from whatever the phase's `run()` returned. This is the canonical event-driven store.
2. **Legacy `TaskRun.*_result` JSONB columns** — mirrored from `PhaseExecution.result` on successful completion via `_LEGACY_RESULT_MAP` at `backend/worker/pipeline.py:350–352`. This is the back-compat path; legacy phase modules and frontend code read directly from these columns.

### Phase signature (today)

```python
async def run(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict | None = None,
) -> None | str | dict
```

Return semantics:
- `None` — phase completed, no structured result.
- `dict` — phase completed; pipeline stores it in `PhaseExecution.result` and mirrors to legacy column.
- `str` — currently only `"awaiting"` is meaningful (parks approval). Anything else is unused.

### Legacy result mapping

From `backend/worker/pipeline.py:62–68`:

```python
_LEGACY_RESULT_MAP = {
    "workspace_setup": "workspace_result",
    "planning": "planning_result",
    "coding": "coding_results",
    "testing": "test_results",
    "reviewing": "review_result",
}
```

Note: `init`, `approval`, and `finalization` are **not** in the map — they communicate via direct attribute writes on the `TaskRun` (see below).

### Phase-by-phase data flow

| Producer | Writes | Consumer | Reads |
|----------|--------|----------|-------|
| `workspace_setup` | `task_run.workspace_result` (via legacy map) + mutates `task_run.workspace_path` to absolute remote path | `init`, `coding`, `testing`, `reviewing` | `task_run.workspace_path` for SSH cwd |
| `init` (`init_phase` module) | `task_run.branch_name` (may copy from `task_source_meta.pr_head_branch`); `task_run.planning_result = {"context_docs": []}` (initialized as empty stub) | `coding`, `reviewing`, `approval`, `finalization` | `task_run.branch_name` for git ops |
| `planning` | `task_run.planning_result = {"subtasks": [...], "context_docs": [...]}` (via legacy map) | `coding` | `planning_result.subtasks` to drive per-subtask agent invocations |
| `coding` | `task_run.coding_results = {session_id, agents: {a, b}, pr_diff, pr_comments, ...}` (via legacy map) | `reviewing` | `coding_results.session_id` (resume agent session); `coding_results.pr_diff` (pre-fetched diff fed to reviewer) |
| `testing` | `task_run.test_results` (via legacy map) | `reviewing` (informational) | optional read |
| `reviewing` | `task_run.review_result` (via legacy map) | `approval`, `finalization` | summary surfaced to humans |
| `approval` | `task_run.pr_url` (after `gh pr create` or `GitProvider.create_pr`); returns `"awaiting"` to park run | `finalization` | `task_run.pr_url` |
| `finalization` | `task_run.completed_at`, status flips | — | `task_run.pr_url`, `task_run.review_result`, `task_run.task_source_meta.pr_head_branch`, `task_run.task_source_meta.pr_number` |

### Other shared state on `TaskRun`

These are not phase-result columns but are read/written across phases:

- `task_run.task_source_meta` (JSONB) — single bag of source metadata. Common keys:
  - `labels: list[str]` — drives the label-match cascade.
  - `pr_head_branch: str`, `pr_number: int` — populated by `pr_fetch` / PR-targeted workflows; read by `init` to set `branch_name` and by `finalization` for cleanup/comments.
  - `agent_override: str`, `phase_overrides: dict`, `workspace_server_id: int` — manual-run plumbing from `POST /runs` (`backend/api/runs.py:73–85`).
  - `issue_number: int`, `issue_url: str`, `skip_schedule: bool`.
- `task_run.workflow_template_id` — if `None` at start, set by `_resolve_workflow_phases` when a template wins (`backend/worker/pipeline.py:135–136`).
- `task_run.current_phase` and `task_run.phase_started_at` — touched by the orchestrator on every transition.

### Awaiting / waiting states

- `PhaseExecution.trigger_mode == "wait_for_trigger"` → pipeline parks the run with `status = "waiting_for_trigger"` *before* execution (`backend/worker/pipeline.py:256–267`).
- `PhaseExecution.trigger_mode == "wait_for_approval"` → pipeline parks the run with `status = "awaiting_approval"` *after* execution (`backend/worker/pipeline.py:378–387`). The phase itself runs to completion first.
- Either way, the orchestrator returns from `execute_pipeline()`; the run is resumed by an external trigger (webhook, manual UI click) which flips the phase row back to `pending`.

---

## 6. Trigger entry points

### Webhook handlers

All under `backend/api/`:

| Handler module | Routes | Purpose |
|----------------|--------|---------|
| `webhooks.py` (365 lines) | `/webhooks/plane`, `/webhooks/github`, `/webhooks/gitea`, `/webhooks/gitlab`, `/webhooks/notion` | Issue events — gated on `"ai-task"` label (or `notion_ai_task_tag` for Notion) |
| `webhooks_pr.py` | PR events | Routes PR-targeted runs |
| `webhooks_pr_comment.py` | PR comment events | Triggers fix/review runs from comments |
| `webhooks_slack.py` | Slack slash commands / events | Manual triggers from Slack |
| `webhooks_discord.py` | Discord events | Manual triggers from Discord |
| `webhooks_linear.py` | Linear issue events | Linear-specific equivalent of `webhooks.py` |
| `webhooks_monitoring.py` | Generic monitoring alert webhooks (sentry/datadog/grafana) | Maps alerts → task via `monitoring_rules` |

### Label-match path: webhook → TaskRun → resolved phases

This is the dominant "trigger" chain today. Trace one full call:

1. **External system POSTs** to e.g. `/api/webhooks/github` with an issue payload.
2. **Handler parses the payload** (`backend/api/webhooks.py:87–136` for GitHub): pulls `action`, `issue`, `repository`. Filters on `action in ("opened", "labeled")` and `"ai-task" in label_names`.
3. **Project lookup** via `ProjectConfigRepository.get_by_git_repo("github", owner, name)`.
4. **TaskRun creation** via `create_task_run(...)` in `backend/services/run_factory.py`. The handler passes `task_source_meta={"issue_number": ..., "repo_full_name": ..., "labels": label_names}` (`backend/api/webhooks.py:118–130`).
5. **Run sits as `pending`** until the worker engine ticks.
6. **`backend/worker/engine.py`** picks up the next pending run and calls `execute_pipeline(run, session, services)`.
7. **`execute_pipeline`** at `backend/worker/pipeline.py:219–230` flips the run to `running`, then calls `_ensure_phase_executions(run, session)`.
8. **`_ensure_phase_executions`** at `backend/worker/pipeline.py:145–153` checks for existing `PhaseExecution` rows; if none, calls `_resolve_workflow_phases(run, session)`.
9. **`_resolve_workflow_phases`** at `backend/worker/pipeline.py:97–142` runs the **resolution cascade**:
   1. Autonomy `execution_mode` (`autonomous` / `hybrid` / `multi_agent`) — fixed sequence, no template.
   2. Explicit `run.workflow_template_id` — load by id.
   3. Label-based: `WorkflowTemplateRepository.match_labels(labels)` where `labels = task_source_meta.get("labels", [])`.
   4. `WorkflowTemplateRepository.get_default()` — `is_default = True`.
   5. Hardcoded `PHASE_NAMES` fallback.
10. **`PhaseExecutionRepository.create_for_run`** materializes one `PhaseExecution` row per `PhaseConfig` from the resolved template's `phases[]`.
11. **Pipeline loop** at `backend/worker/pipeline.py:236–399` picks the next `pending` `PhaseExecution`, looks the module up via `_get_phase_module()` (which consults the auto-discovered registry), and dispatches `await phase_mod.run(run, session, services, phase_config=...)`.

### Other entry points (not webhook-driven)

- **Manual** — `POST /runs` at `backend/api/runs.py:55–125`. Accepts `labels`, `workflow_template_id`, `phase_overrides`, `agent_override`, `workspace_server_id`. Same downstream pipeline; just bypasses the webhook parsing.
- **Polling** — `backend/worker/issue_poller_scheduler.py` ticks every 60s and dispatches per-project pulls. Individual pollers live in `backend/services/task_source_polling/` (`github_poller.py`, `gitea_poller.py`, `gitlab_poller.py`, `plane_poller.py`, `notion_poller.py`, sharing the `protocol.py` Protocol and `factory.py` factory). Each poller calls `create_task_run(...)` exactly like a webhook handler would.
- **Automation rules** — `backend/models/automation_rules.py` defines event-driven rules; `backend/services/rules_dispatcher.py:17–26` subscribes to broadcaster global events:

  ```python
  _TRIGGERABLE_EVENTS = {
      "run_started",
      "run_completed",
      "run_failed",
      "phase_completed",
      "phase_failed",
      "phase_waiting",
      "approval_requested",
      "cost_threshold_exceeded",
  }
  ```

  Rules fire on these and can create follow-up runs.
- **Monitoring rules** — `backend/models/agents.py:133–146`. Per-project mapping from external alert source (sentry / datadog / grafana / etc.) → task template. Driven by `/webhooks/monitoring*` endpoints.
- **Platform crons** — `backend/models/platform_crons.py`. Cron-scheduled prompts dispatched into a local tmux session. **Not** a TaskRun source — separate lane for ambient autonomous activity.

---

## 7. Pipeline orchestration loop (one-screen mental model)

For readers who want the whole shape on one page, the loop at `backend/worker/pipeline.py:219–421`:

```text
execute_pipeline(run, session, services):
    run.status = "running"
    emit run_started
    _ensure_phase_executions(run, session)         # materialize PhaseExecution rows once
    _skip_phases_for_consolidated(...)             # may flip planning/reviewing to "skipped"
    loop:
        phase_exec = next pending PhaseExecution by order
        if none: break
        if phase_exec.trigger_mode == "wait_for_trigger":
            mark phase_exec waiting, run.status = waiting_for_trigger
            return                                  # park
        mark phase_exec running
        try:
            result = await phase_mod.run(run, session, services, phase_config=...)
        except SSHCommandError | Exception:
            retry up to phase_exec.max_retries, then mark failed and return
        mark phase_exec completed with result
        mirror result into TaskRun.<legacy_attr> via _LEGACY_RESULT_MAP
        if phase_exec.trigger_mode == "wait_for_approval":
            mark phase_exec waiting, run.status = awaiting_approval
            return                                  # park
        sleep delay_seconds if configured
    run.status = "completed"
    emit run_completed
```

---

## 8. What this snapshot does NOT cover

These are deliberately out of scope here. They live in their own docs or in the plan:

- **`ServiceContainer` shape** — see `backend/services/container.py`. The pipeline passes it through opaquely.
- **Phase-by-phase business logic** — each phase module's internals. Only the I/O contract is captured above.
- **Agent / role resolution** — `RoleResolver`, `CLIAdapter`, `RoleAdapter` Protocol. See ADR-005.
- **Workspace server SSH plumbing** — `SSHService`, `CommandExecutor`. See ADR-003.
- **Worktree strategy** — none today; arrives in Phase 4 of the overhaul.

---

## 9. Verification checklist for future readers

Before relying on this doc, re-run:

```bash
# Phase module discovery is the runtime truth
docker compose -f docker-compose.dev.yml exec backend python -c \
  "from backend.worker.phases.registry import discover_phases; print(sorted(discover_phases()))"

# Confirm the cascade lines still match
docker compose -f docker-compose.dev.yml exec backend grep -n "PHASE_NAMES\|_LEGACY_RESULT_MAP\|_AUTONOMOUS_PHASE_SEQUENCES" backend/worker/pipeline.py

# Confirm match_labels still uses OR-of-AND alphabetical
docker compose -f docker-compose.dev.yml exec backend grep -n "match_labels\|_rules_match" backend/repositories/workflow_template_repo.py
```

If any of those drift from what's documented above, update this file before continuing.

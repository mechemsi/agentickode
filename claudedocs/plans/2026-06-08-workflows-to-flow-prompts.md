---
title: "Replace workflow templates with flow prompts"
status: planned
date: 2026-06-08
related:
  - claudedocs/decisions/007-composable-step-workflows.md
  - claudedocs/decisions/008-direct-agent-selection.md
  - claudedocs/plans/2026-05-23-agentic-workflow-overhaul.md
  - claudedocs/implementations/2026-06-05-remove-roles.md
---

# Replace Workflow Templates with Flow Prompts

> **DECISIONS (2026-06-08, Dominykas)** — direction locked, implementation still paused:
> - **Option B (full simplification): a flow prompt = a single agent call.** The agent's
>   return becomes the run status; AgenticKode auto-assembles surrounding data, the user
>   only defines the prompt. (Resolves OQ-9.)
> - **Supersede ADR-007** — multi-step bash+agent composition is removed. (Resolves OQ-4.)
> - **Break custom multi-step templates** — no migration path. (Resolves OQ-3.)
> - **PR-review is also a flow prompt** — same single-call mechanism, different prompt. (Resolves OQ-6.)
>
> **RESOLVED (2026-06-09) — see [ADR-009](../decisions/009-flow-prompts.md), accepted:**
> - OQ-1 → **drop** `phase_executions`; result → `task_runs.coding_results`.
> - OQ-2 → data is **fixed per flow type** AND additionally **declarable per prompt**.
> - OQ-5 → **deprecate** comparison (A/B) mode.
> - OQ-7 → **drop** the `workflow_templates` table; null the FK (irreversible, accepted).
>
> Implementation is now unblocked; ADR-009 defines a 5-phase rollout (additive first, table drops last).
>
> **Phase 1 (additive, flag-gated) — DONE 2026-06-09** (`flow_prompts` table + `flow_prompt_id` +
> data-source registry + `execute_flow_prompt` executor + `FLOW_PROMPTS_ENABLED` flag, off by
> default; seed). See [implementation](../implementations/2026-06-09-flow-prompts-phase1.md).
>
> **Phase 2 (PR-review on a flow prompt) — DONE 2026-06-09** (poller + webhook bind PR-review runs
> to the `pr-review` flow prompt when the flag is on; executor sets `review_result` so finalization
> posts the comment + flips the label — parity with the template path).
> See [implementation](../implementations/2026-06-09-flow-prompts-phase2-pr-review.md).
>
> **Phase 3 (default + deprecate templates) — DONE 2026-06-09** (flag on → runs with no explicit
> flow prompt default to the `implement` flow prompt; template creation logs a deprecation warning).
> See [implementation](../implementations/2026-06-09-flow-prompts-phase3-default.md).
>
> **Both flows validated live** (real agent output): PR-review #48 + implement #51; 7 bugs fixed.
> See [validation](../implementations/2026-06-09-flow-prompts-validation.md).
>
> **Phase 4 — DONE 2026-06-09** (frontend UI removal + comparison removal):
> - 4a: comparison (A/B) mode removed (`_comparison.py`, coding-phase branch, pick-winner
>   endpoint + `PickWinnerRequest`, frontend `ComparisonResultsPanel`/types/api).
> - 4b: WorkflowTemplates UI removed — page, step editors, nav link, route; untangled the
>   `NewRun` template selector, `Dashboard`/`TaskRunTable` workflow-name column, and `RunDetail`
>   workflow display; deleted `api/workflows.ts`. Backend template API/model **kept** (Phase 5).
>
> **Phase 5 (irreversible) held** — needs flow prompts as the working prod default first
> (durable non-root claude-worker provisioning + flag-on + devbox claude auth).

> **WARNING — PRE-DESIGN DOCUMENT**: This plan maps the current system and
> sketches the replacement model. It contains many open questions that require
> explicit product decisions before any code is written. An ADR (009) must be
> accepted first. This is a *larger architectural risk than the roles removal
> (ADR-008)*. The roles removal deleted ~3 200 lines of unused indirection;
> this task proposes removing the *core scheduling/routing layer* of the engine.

---

## Goal

Replace the `WorkflowTemplate` + `PhaseExecution` step-dispatch abstraction
with "flow prompts": a single agent prompt combined with fetched runtime data
that an agent executes end-to-end, without the platform prescribing which
phases/steps run.

---

## Current Architecture — What Actually Exists

### Data layer

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `workflow_templates` | Named bags of steps with routing rules | `phases` (JSONB array of `PhaseConfig`), `triggers` (JSONB), `label_rules` (JSONB), `is_default`, `is_system` |
| `task_runs` | Run state machine | `workflow_template_id` (FK → workflow_templates, nullable), `execution_mode`, `task_source_meta` (JSONB carries `review_mode`, `labels`, `pr_url`, etc.), legacy result columns (`planning_result`, `coding_results`, `test_results`, `review_result`) |
| `phase_executions` | One row per step in a run | `phase_name`, `order_index`, `phase_config` (JSONB), `kind` (via config), `trigger_mode`, `status`, `result` (JSONB), `retry_count` |
| `agent_invocations` | Per-agent-call audit/cost log | FK → `phase_executions` |

**Models**: `backend/models/workflows.py:WorkflowTemplate`, `backend/models/runs.py:PhaseExecution`, `backend/models/runs.py:TaskRun`.

### Step dispatch (`backend/worker/pipeline.py`)

`execute_pipeline()` is the single entry point. It calls:

1. `_resolve_workflow_phases(run, session)` — builds the ordered list of step dicts:
   - **Priority 0**: `task_source_meta["review_mode"]` → hard-pins to the `pr-review` template (never falls through; fails loudly if template is missing).
   - **Priority 1**: `autonomy_config.execution_mode` in `{autonomous, hybrid, multi_agent}` → uses `_AUTONOMOUS_PHASE_SEQUENCES` (hardcoded lists in `pipeline.py:46–50`), bypasses templates entirely.
   - **Priority 2**: explicit `run.workflow_template_id`.
   - **Priority 3**: `TriggerMatcher` / `label_rules` match on `task_source_meta["labels"]`.
   - **Priority 4**: default template (`is_default=True`).
   - **Priority 5**: hardcoded `PHASE_NAMES` list.
2. `_ensure_phase_executions()` — creates `PhaseExecution` rows from the resolved list.
3. A `while True` loop that calls `_dispatch_step()` for each pending `PhaseExecution`.

`_dispatch_step()` branches on `phase_config["kind"]`:

| Kind | Handler |
|------|---------|
| `"bash"` | `backend/worker/steps/bash_step.py:run_bash_step` |
| `"agent"` | `backend/worker/steps/agent_step.py:run_agent_step` |
| `"legacy_phase"` | auto-discovered module from `backend/worker/phases/registry.py` |

### Step kinds and phase modules

The registry (`backend/worker/phases/registry.py:discover_phases`) scans all
non-`_`-prefixed modules in `backend/worker/phases/` for a `run()` coroutine.
Currently discovered:

| Phase module | PHASE_META kind | Notes |
|-------------|----------------|-------|
| `workspace_setup` | `builtin` | Clones repo, sets up worktree |
| `init_phase` (name="init") | `builtin` | Branch init, git env |
| `approval` | `legacy_phase` | Push branch + create PR; parking via `trigger_mode=wait_for_approval` |
| `coding` | `legacy_phase` | Subtask decomposition; wraps `_comparison.py` for A/B mode |
| `planning` | `legacy_phase` | Subtask planning |
| `reviewing` | `legacy_phase` | Code review pass; also used by `pr-review` template for AI review |
| `testing` | `legacy_phase` | Test runner |
| `finalization` | `legacy_phase` | Cleanup + post PR comment for `review_mode="comment"` |
| `agent_loop` | `legacy_phase` | Autonomous/episodic mode — Claude Code drives end-to-end |
| `pr_fetch` | `legacy_phase` | Fetches PR diff/comments via provider API (no SSH) |
| `task_creation` | `legacy_phase` | Spawns sub-tasks |

Generic steps: `bash` and `agent` (ADR-007). `agent_step.py:run_agent_step`
uses `AgentResolver.resolve_agent()` + `adapter.generate(rendered_prompt)` or
`adapter.run_task(workspace, rendered_prompt)`. Prompt templating is in
`backend/worker/steps/templating.py` (`{{run.FIELD}}`, `{{steps.NAME.FIELD}}`).

### Seeded templates

Three system templates (`backend/seed/workflow_templates.py`):

| Template name | Description | Phases |
|--------------|-------------|--------|
| `default` | Standard implement flow | `workspace_setup → init → implement (kind:agent) → approval → finalization` |
| `example-composable` | Demo of bash+agent | `workspace_setup → init → build (bash) → implement (agent) → deploy (bash)` |
| `pr-review` | AI PR review | `pr_fetch → reviewing → finalization` |

`seed_workflow_templates()` runs at startup; it also prunes deprecated system
templates and upgrades the old 8-phase default shape to the 5-step one.

### Trigger / routing layer

- `WorkflowTemplate.triggers` (JSONB) — typed trigger rules: `label`, `issue_event`, `pr_event`, `schedule`, `manual`.
- `TriggerMatcher` (`backend/services/triggers/matcher.py`) — resolves an event to a template; used by webhook handlers and the schedule scheduler.
- `WorkflowTemplate.label_rules` — legacy label matching; still in DB but `TriggerMatcher` supersedes it for new routing.
- **Schedule triggers**: `backend/worker/schedule_trigger_scheduler.py` polls all templates with `schedule` triggers and fires runs.
- **PR review poller**: `backend/services/task_source_polling/pr_review_poller.py` polls for PRs with `ai-review` label; hard-depends on `WorkflowTemplateRepository.get_by_name("pr-review")`.
- **Webhook handlers**: `backend/api/webhooks.py`, `webhooks_pr.py`, `_pr_webhook_helpers.py` — all use `TriggerMatcher` or directly fetch the `pr-review` template by name.

### Approval gate

`trigger_mode="wait_for_approval"` on a `PhaseExecution` parks the run:
`pipeline.py:464–473` sets `run.status="awaiting_approval"` and returns.
A separate API call resumes it. This is the only human-gate mechanism.

### Comparison mode

`backend/worker/phases/_comparison.py:run_comparison()` — called from
`coding.py` when `phase_config["params"]["comparison"]` is present.
Creates parallel branches, runs two agents concurrently, stores results in
`task_run.coding_results`, parks run waiting for user to pick a winner.

### Backup / export

`backend/services/backup/entity_registry.py:113–116` — `workflow_templates`
is a registered export entity. Backup archives include all user-created
templates.

### Frontend

| File | Role |
|------|------|
| `frontend/src/pages/WorkflowTemplates.tsx` (397 lines) | Full CRUD UI for workflow templates |
| `frontend/src/components/workflows/StepListEditor.tsx` (124 lines) | Step ordering/enable toggle |
| `frontend/src/components/workflows/StepEditor.tsx` (224 lines) | Per-step kind/params editor |
| `frontend/src/pages/NewRun.tsx` (490 lines) | Run creation — template picker dropdown |
| `frontend/src/components/runs/TaskRunTable.tsx` | Shows `workflow_template_id` column |
| `frontend/src/api/workflows.ts` | All workflow template API calls |
| `frontend/src/types/workflows.ts` | `WorkflowTemplate`, `PhaseConfig`, `StepKind` types |

---

## Proposed "Flow Prompts" Model

The feature request as stated: **drop `WorkflowTemplate`; replace it with a
"flow prompt" — a prompt the platform sends to an agent together with fetched
context data**.

Based on the analogy to "Paperclip" (an autonomous agent given a goal), the
model appears to be:

1. **A run is defined by a prompt + fetched data**, not by a list of phases.
2. **The agent decides what steps to take** — fetch context, write code, commit,
   create PR — without the platform prescribing a phase sequence.
3. **Flow prompts are per-project or global** (similar to how roles were once
   per-server) and can reference template variables (`{{run.title}}`,
   `{{run.description}}`).

### What a flow prompt would be (sketch)

```yaml
# A "FlowPrompt" entity (new DB table or ProjectConfig field)
name: "default-implement"
prompt: |
  Task: {{run.title}}

  {{run.description}}

  Implement this task end-to-end.  Stage, commit, push, and open a PR.
fetched_data:        # platform fetches this before handing to agent
  - kind: repo_context   # README, recent commits, open issues
  - kind: pr_diff        # for review-mode runs
agent: null              # null → project/global default
timeout_seconds: 3600
```

The pipeline would: (1) run `workspace_setup` + `init` (always); (2) render
the prompt with fetched data; (3) invoke the agent once via `run_task`; (4)
gate on approval (if configured); (5) run finalization.

### How a run would execute (proposed)

```
run created
  → workspace_setup (builtin)
  → init (builtin)
  → [fetch configured data_sources]
  → render flow prompt ({{run.*}} + fetched vars)
  → agent.run_task(workspace, rendered_prompt)  # single shot
  → [optional: wait_for_approval gate]
  → finalization (cleanup + PR comment posting)
```

No `PhaseExecution` rows beyond the four fixed steps; no `WorkflowTemplate`.

### What replaces trigger/label routing

This is the biggest open question (see Risks section). Options:

- **A**: `FlowPrompt` rows carry the same `triggers[]` field as `WorkflowTemplate` did. `TriggerMatcher` resolves to a `FlowPrompt` instead of a template.
- **B**: Routing moves entirely to per-project config — a project declares its flow prompt; all runs for that project use it. PR-review becomes a special flow prompt bound to `review_mode`.
- **C**: Drop structured routing; every run carries its prompt inline at creation time (maximum flexibility, no server-side template store).

### How PR-review fits

PR-review is the hardest compatibility case. It:

- Is hard-detected via `task_source_meta["review_mode"]` in `pipeline.py:163–179`.
- Uses three specific phases: `pr_fetch` (API call, no SSH), `reviewing` (generate mode, not task mode), `finalization` (posts comment, does NOT push/cleanup).
- Is triggered by three separate entry points: PR webhook label event, CI `POST /api/webhooks/pr-review`, PR review poller.
- Has a guard in `pipeline.py:158–179` that **prevents** any execution_mode override from hijacking a PR review run.

In the flow-prompt model, PR-review would need to be a named flow prompt
(e.g. `pr-review`) that: (a) fetches `pr_diff` as its data source; (b) uses
`generate` mode, not `task` mode; (c) skips workspace setup; (d) posts a
comment in finalization instead of pushing. All of this is currently encoded
in the `reviewing.py` and `finalization.py` phase modules — it would need to
be either re-expressed in the flow prompt schema or kept as a special case.

### How comparison mode fits

Comparison mode is currently triggered by `phase_config["params"]["comparison"]`
on the coding step. In a flow-prompt model with no phases, comparison has no
natural home unless the flow prompt schema gains a `comparison` field or
comparison becomes its own flow prompt variant. This is an open question.

### How approval gate fits

`trigger_mode="wait_for_approval"` is currently a per-`PhaseExecution` field.
In a single-step flow-prompt model, approval must become a run-level flag (it
already is, partially — `run.status="awaiting_approval"`). The approval resume
API (`POST /api/runs/{id}/approve`) would remain unchanged.

---

## Scope

### In Scope

- [ ] Define the `FlowPrompt` data model (new table or embed in `ProjectConfig`)
- [ ] Replace `_resolve_workflow_phases` + `_ensure_phase_executions` with single-step dispatch
- [ ] Migrate seeded templates to flow prompts (`default-implement`, `pr-review`)
- [ ] Update `TriggerMatcher` / routing to resolve to flow prompts instead of templates
- [ ] Update PR review poller + webhook handlers to reference flow prompt by name/type
- [ ] Remove or deprecate `WorkflowTemplate` table and CRUD API
- [ ] Remove `PhaseExecution` rows for dynamic steps (or repurpose as a single execution record)
- [ ] Frontend: replace `WorkflowTemplates.tsx` and step editors with flow prompt editor
- [ ] DB migrations: add `flow_prompts` table; remove (or keep) `workflow_templates`
- [ ] Update backup/export entity registry

### Out of Scope

- Removing `workspace_setup` and `init` phase modules (stay as builtins)
- Removing `approval` and `finalization` logic (stays, possibly as builtin steps)
- Removing `AgentInvocation` cost tracking
- Removing `PhaseExecution` table entirely (historical run audit needs it, or needs a replacement)
- Changing the agent adapter / `AgentResolver` layer (ADR-008, already done)
- Multi-agent / parallel execution mode changes

---

## Migration Strategy

### Phase 0 — Design decision (blocker)

**An ADR (009) must be written and accepted before any code is written.**
Key decisions needed (see Risks):

1. Does `PhaseExecution` stay as the execution record, or is it replaced?
2. Does `WorkflowTemplate` stay as the routing table (renamed), or is it deleted?
3. How does PR-review remain first-class without a template?
4. What happens to user-created custom templates?

### Phase 1 — Add `FlowPrompt` as an additive layer

Add a `flow_prompts` table (new migration `041`). Seed `default-implement` and
`pr-review` flow prompts. Run the new single-step dispatch path in parallel
with the existing `WorkflowTemplate` path, controlled by a feature flag
(`ProjectConfig.use_flow_prompt: bool`, default `false`). No regressions;
existing runs continue on the template path.

### Phase 2 — Route PR-review through flow prompt

Update `pipeline.py` `review_mode` guard to use the `pr-review` flow prompt
instead of the `pr-review` template. Update poller + webhook handlers.
Validate that `pr_fetch`, `reviewing`, and `finalization` logic is fully
expressed in the flow prompt (or kept as named builtins).

### Phase 3 — Default to flow prompt for new projects

New projects get `use_flow_prompt=true` by default. Existing projects stay on
template path. Validates the new path in production.

### Phase 4 — Migration UI + operator communication

Provide a "Migrate to flow prompts" action in the UI. Document what breaks
(custom templates, step overrides).

### Phase 5 — Deprecate `WorkflowTemplate` CRUD

Hide `WorkflowTemplates` page behind a feature flag. Warn operators who still
have non-system templates. Give a one-release grace period.

### Phase 6 — Remove `WorkflowTemplate` (breaking)

Drop `workflow_templates` table. Drop `WorkflowTemplates.tsx`. This is
irreversible. Remove from backup entity registry or migrate backup format.

---

## What Breaks (Explicit List)

| Subsystem | Impact | Severity |
|-----------|--------|----------|
| **PR-review** | Hard-coded to `pr-review` template name in poller (`pr_review_poller.py:99`), webhook handler (`webhooks_pr.py:111`), and pipeline guard (`pipeline.py:166`). Must all be updated atomically. | Critical |
| **Schedule triggers** | `schedule_trigger_scheduler.py` iterates `workflow_templates` looking for `schedule` triggers. If the table is removed, scheduled runs stop firing. | Critical |
| **User-created templates** | Any operator who created custom templates via the UI loses them. There is no migration path unless templates are converted to flow prompts. | High |
| **`task_runs.workflow_template_id`** | FK to `workflow_templates.id`; removing the table breaks the FK. All existing run history loses its template linkage. | High |
| **Backup archives** | Existing backup JSON files contain `"workflow_templates"` keys. Import would fail or silently skip the key. | Medium |
| **`PhaseExecution` rows** | If the table is removed, all historical step-level logs and results are lost. If kept, it needs a new purpose (single execution record per run). | High |
| **A/B comparison mode** | Currently triggered by `coding` phase config. Has no natural home in a single-prompt model. | Medium |
| **Approval gate** | Currently per-`PhaseExecution`. In single-step model, must be a run-level config. Resume API likely unchanged but needs validation. | Medium |
| **Autonomous/hybrid execution modes** | `_AUTONOMOUS_PHASE_SEQUENCES` bypasses templates today. In a flow-prompt world these become different flow prompt variants. | Medium |
| **`example-composable` template** | This is a demo of composable bash+agent steps (ADR-007). Its value proposition disappears if the flow-prompt model offers only a single agent invocation. | Low |
| **Frontend tests** | `RunDetail.test.tsx`, `NewRun.test.tsx`, `Dashboard.test.tsx` all reference `workflow_template_id`. | Low |

---

## Data Model / Migration Changes

### New table (migration `041`)

```sql
CREATE TABLE flow_prompts (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    prompt      TEXT NOT NULL,           -- {{run.X}} / {{steps.X.Y}} templating
    data_sources JSONB NOT NULL DEFAULT '[]',  -- fetched context config
    agent       TEXT,                    -- NULL → project/global default
    timeout_seconds INTEGER,
    trigger_mode TEXT NOT NULL DEFAULT 'auto',  -- 'auto' | 'wait_for_approval'
    triggers    JSONB NOT NULL DEFAULT '[]',    -- same schema as WorkflowTemplate.triggers
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    is_system   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `project_configs` change (migration `041`)

```sql
ALTER TABLE project_configs ADD COLUMN flow_prompt_id INT REFERENCES flow_prompts(id);
ALTER TABLE project_configs ADD COLUMN use_flow_prompt BOOLEAN NOT NULL DEFAULT FALSE;
```

### `task_runs` changes

- Add `flow_prompt_id INT REFERENCES flow_prompts(id)` (nullable, like `workflow_template_id`).
- Eventually drop `workflow_template_id` (Phase 6 migration, irreversible).
- Legacy result columns (`planning_result`, `coding_results`, etc.) — already scheduled for removal in 0.7.0 per ADR-007.

### Tables to eventually drop (Phase 6, irreversible)

- `workflow_templates`
- `phase_executions` (or repurpose as `step_executions` with one row per run)

---

## Coupling and Blast Radius

Every file that would need to change, grouped by subsystem:

**Pipeline / worker engine**
- `backend/worker/pipeline.py` — gut `_resolve_workflow_phases`, `_ensure_phase_executions`, `_skip_phases_for_consolidated`; replace with flow-prompt dispatch
- `backend/worker/phases/registry.py` — may become unused if legacy phases are removed
- `backend/worker/phases/` (all modules) — `approval`, `finalization`, `planning`, `coding`, `testing`, `reviewing`, `pr_fetch`, `agent_loop` — some become redundant, some become builtins
- `backend/worker/steps/agent_step.py` — the new dispatch core; may need `run_task` mode + data-source pre-fetching
- `backend/worker/phases/_comparison.py` — no natural home; needs explicit design decision

**Models / DB**
- `backend/models/workflows.py` — `WorkflowTemplate` (drop or keep as read-only)
- `backend/models/runs.py` — `PhaseExecution` (repurpose or drop), `TaskRun` (add `flow_prompt_id`)
- New `backend/models/flow_prompts.py`

**Repositories**
- `backend/repositories/workflow_template_repo.py` — drop or repurpose
- New `backend/repositories/flow_prompt_repo.py`
- `backend/repositories/phase_execution_repo.py` — drop or repurpose

**API routes**
- `backend/api/workflow_templates.py` (251 lines) — drop or replace with flow prompt CRUD
- `backend/api/runs.py` — update `RunCreateRequest` (swap `workflow_template_id` for `flow_prompt_id`)
- `backend/api/webhooks.py` — update `TriggerMatcher` call
- `backend/api/webhooks_pr.py` — update `pr-review` template lookup to flow prompt
- `backend/api/_pr_webhook_helpers.py` — `build_pr_review_run` references `workflow_template_id`

**Services**
- `backend/services/triggers/matcher.py` — resolve to `FlowPrompt` instead of `WorkflowTemplate`
- `backend/services/run_factory.py` — swap `workflow_template_id` arg
- `backend/services/task_source_polling/pr_review_poller.py` — remove `get_by_name("pr-review")` template lookup
- `backend/services/backup/entity_registry.py` — swap export entity

**Seed**
- `backend/seed/workflow_templates.py` — rewrite as `flow_prompts.py`

**Scheduler**
- `backend/worker/schedule_trigger_scheduler.py` — scan `flow_prompts` instead of `workflow_templates`

**Schemas**
- `backend/schemas/workflows.py` — `PhaseConfig`, `WorkflowTemplateCreate`, etc. — all change or are replaced

**Frontend (745 lines across 3 files + types)**
- `frontend/src/pages/WorkflowTemplates.tsx` — drop and replace with `FlowPrompts.tsx`
- `frontend/src/components/workflows/StepListEditor.tsx` — drop
- `frontend/src/components/workflows/StepEditor.tsx` — drop
- `frontend/src/pages/NewRun.tsx` — swap template picker for flow prompt picker
- `frontend/src/components/runs/TaskRunTable.tsx` — swap `workflow_template_id` column
- `frontend/src/api/workflows.ts` — replace with `flowPrompts.ts`
- `frontend/src/types/workflows.ts` — replace `WorkflowTemplate`/`PhaseConfig` types
- `frontend/src/main.tsx` — update router (remove `WorkflowTemplates` page)

**Tests**
- `frontend/src/__tests__/NewRun.test.tsx`, `RunDetail.test.tsx`, `Dashboard.test.tsx`, `types.test.ts` — all reference `workflow_template_id`
- Backend unit tests for `pipeline.py`, `workflow_template_repo.py`, `triggers/matcher.py`

**Alembic**
- Migration `041` (add `flow_prompts`, `project_configs.use_flow_prompt`)
- Migration `042` (add `task_runs.flow_prompt_id`)
- Migration `04X` (drop `workflow_templates`, `phase_executions`) — Phase 6 only, irreversible

---

## Success Criteria

- [ ] A new project can be configured with a flow prompt and run an `implement` task end-to-end without a `WorkflowTemplate` row existing
- [ ] PR-review (poller + webhook + CI endpoint) works unchanged after the `pr-review` template is replaced by a `pr-review` flow prompt
- [ ] Schedule triggers fire correctly from `flow_prompts.triggers` instead of `workflow_templates.triggers`
- [ ] The approval gate (`wait_for_approval`, human resume) works in the flow-prompt path
- [ ] Backup export/import round-trips flow prompts correctly
- [ ] Existing runs with `workflow_template_id` set continue to display correctly in the UI (read-only history)
- [ ] All backend tests pass; coverage ≥ 70%
- [ ] All frontend tests pass
- [ ] No regressions on the current default deploy path during the feature-flag phase

---

## Risks and Open Questions

**This section is the most important part of this document.**

This change has a substantially larger blast radius than ADR-008 (roles
removal). ADR-008 removed an unused indirection layer with no external
callers. This change removes the platform's *core dispatch model*. Every run,
every webhook, every scheduled job, PR review, and comparison mode is
currently built on top of `WorkflowTemplate`. The risks below must each
receive an explicit decision before implementation.

### OQ-1: Does `PhaseExecution` stay?

The `phase_executions` table is the audit trail for step-level results,
timing, and cost (`AgentInvocation.phase_execution_id` FK). Dropping it
loses all historical step detail. Options:

- **A** — Keep as a single-row-per-run execution record (repurposed, not dropped).
- **B** — Replace with a lighter `run_executions` table (1 row per run, JSONB result).
- **C** — Drop entirely; move result into `task_runs.coding_results` JSONB.

**Decision required before implementation.**

### OQ-2: What is a "data source" in a flow prompt?

The PR-review flow needs to fetch a PR diff before the prompt. An implement
flow needs workspace context. If flow prompts declare `data_sources[]`, the
platform must implement fetching for each kind (`repo_context`, `pr_diff`,
`issue_body`, etc.). This is new infrastructure, not just renaming existing
tables. How much of this should be in the prompt itself vs. platform-fetched?

### OQ-3: How do custom templates migrate?

Users who created custom `WorkflowTemplate` rows via the UI — with custom
step sequences, bash steps, multi-agent pipelines — have no migration path
to flow prompts unless the flow prompt model supports everything the template
model did. If the flow prompt model is strictly simpler (one agent call), custom
multi-step workflows break permanently. The task framing ("with agentic flows,
static workflows are legacy") implies this is intentional — but it is a
breaking change for any user who relied on composable bash+agent steps
(the feature ADR-007 specifically added). **This needs explicit sign-off.**

### OQ-4: What happens to composable bash+agent steps (ADR-007)?

ADR-007 was accepted 2026-05-23 and invested significant design effort in
supporting multi-step bash+agent composition. ADR-007 was motivated by the
argument that "the flexibility we need is already in the storage layer". The
current task proposes removing that layer three weeks after it was ratified.
If flow prompts replace multi-step composition entirely:

- The `example-composable` template (bash → agent → bash) has no equivalent.
- Workflows like "run tests → if they fail, call agent to fix → run tests again" require either (a) a flow prompt schema that supports conditional steps, or (b) encoding all of that in the agent prompt and trusting the agent to handle it.

**Is the intent to remove multi-step composition, or to replace the storage
format while preserving the capability?**

### OQ-5: How does comparison (A/B) mode work?

`_comparison.py` is wired to the `coding` phase. It creates parallel branches
and runs two agents concurrently. In a single-prompt flow model there is no
`coding` phase to hang it on. Options:

- A `comparison` flag on the flow prompt that the pipeline expands into two
  parallel agent invocations.
- Comparison becomes its own flow prompt type.
- Comparison is deprecated alongside multi-step templates.

### OQ-6: How do PR-review `generate` vs. `task` modes work?

The current `reviewing` phase uses `adapter.generate(prompt)` (not
`run_task`), because PR review doesn't require a workspace checkout — it
reads a diff from the API. The `agent_step.py` `run_agent_step` supports both
modes via `params["mode"]`. But a flow prompt that "skips workspace setup"
and runs in `generate` mode is structurally different from an implement flow
that runs `run_task` in a checked-out worktree. Does the flow prompt schema
expose this distinction, or is PR-review always a special case?

### OQ-7: What is the DB migration strategy for `workflow_template_id` on `task_runs`?

Removing the FK requires either:
- Keeping `workflow_templates` table as read-only (no CRUD API, no UI) so
  existing run history can still join to it.
- NULLing the FK and dropping the table (existing runs lose template linkage).
- Migrating `workflow_template_id` to store the template name as a text field.

This is irreversible. Historical runs in production cannot be recovered after
the table is dropped.

### OQ-8: Effort estimate

Rough sizing based on the blast radius map above:

| Phase | Scope | Estimate |
|-------|-------|----------|
| 0 — ADR + design | Schema decisions, OQ-1 through OQ-7 | 1–2 days design |
| 1 — Add `flow_prompts` table + feature flag | Migration, seed, repo, pipeline fork | 3–4 days |
| 2 — PR-review on flow prompt | Poller, webhooks, pipeline guard | 2–3 days |
| 3 — Default to flow prompt, deprecate templates | Project config, UI flag | 2 days |
| 4 — Remove `WorkflowTemplates` UI | Frontend (745 lines) + new flow prompt editor | 3–5 days |
| 5 — Remove `WorkflowTemplate` API + table | Backend (251 line API + repo + seed), migrations | 2–3 days |
| **Total** | | **~13–19 days** |

This estimate does not account for rework if OQ-3 (custom template migration)
requires a translation layer, or if OQ-5 (comparison mode) needs a new design.

### OQ-9: Should this task be broken into two separate tasks?

Option A: **Rename only** — rename `WorkflowTemplate` to `FlowPrompt` in the
DB and UI, keep the step-sequence capability, but simplify the default
template to a single `agent` step. This is low-risk (~2 days), satisfies the
"drop the 'workflow' framing" goal, and preserves multi-step capability for
power users.

Option B: **Full removal** — as described in this document. High-risk, 3–4
week effort, breaks custom templates permanently.

**Recommendation**: Decide option A vs. B before writing any code. If the
goal is purely renaming/reframing, Option A is far safer. If the goal is
genuinely simplifying the execution model to a single agent call, Option B
requires answers to OQ-1 through OQ-7.

---

## Pre-Implementation Requirement

**Do not begin implementation until ADR-009 is written and accepted.**

ADR-009 must answer, at minimum: OQ-1 (PhaseExecution fate), OQ-2 (data
sources), OQ-3 (custom template migration), OQ-4 (composable steps fate),
OQ-5 (comparison mode), and OQ-9 (Option A vs. Option B scope).

The implementation plan above (Phases 1–6) should be treated as a sketch
until those decisions are locked. Each phase should be a separate PR with its
own review gate.

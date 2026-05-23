---
title: Agentic Workflow Overhaul — From Fixed Pipeline to Composable Steps
status: planned
date: 2026-05-23
related:
  - claudedocs/decisions/005-multi-agent-pipeline.md
  - docs/WORKER_PIPELINE.md
  - www/content/docs/guides/worker-pipeline.md
---

# Agentic Workflow Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Replace the fixed 8-phase pipeline narrative with a dynamic, agent-first model where every step is a composable atom (bash or agent invocation with rules), workflows are trigger-driven, and the framework's existing per-phase flexibility becomes the headline UX.

**Architecture:** The DB layer already supports this (`WorkflowTemplate.phases` JSONB, `PhaseExecution.phase_config`, auto-discovered phase registry, `CommandExecutor` for bash, `CLIAdapter.generate` for agents) — what's missing is (a) generic step primitives so non-domain steps don't require a new phase module, (b) trigger configuration on workflows as a first-class field, (c) frontend that exposes step composition instead of just per-phase tweaks, (d) honest docs that describe what the system actually does. We will NOT do a big-bang rewrite — `workspace_setup` and `init` remain built-in immutable preludes; legacy phase modules continue to be discoverable; existing templates keep working. New surface area is additive, old narrative is then deprecated and the docs catch up.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Alembic / Pydantic v2 (backend); React 18 / TS / Vite / Tailwind (frontend); Nuxt 4 / @nuxt/content / Vue 3 (www marketing site); Docker Compose dev environment; PostgreSQL.

**Reference inputs (must read before starting):**
- `claudedocs/research/2026-05-23-current-pipeline-state.md` (synthesized below — write it as task 0)
- `/home/domas/projects/myDash/backend/host-gateway/app/fix_issue.py` — worktree pattern to steal
- `/home/domas/projects/myDash/backend/host-gateway/app/workers.py` — PTY registry, env sanitization, one-shot tickets
- `backend/worker/pipeline.py` (the current orchestrator)
- `backend/schemas/workflows.py` (the existing `PhaseConfig` shape)
- `backend/services/workspace/command_executor.py` (the bash primitive already exists)

---

## Foundation Principles

1. **Two atom types, that's it.** Every non-built-in step is either `bash` or `agent`. No new step types until v2 — we'll discover what's missing once people use it.
2. **`workspace_setup` and `init` are not steps.** They are an immutable prelude that always runs. The "workflow" the user composes is everything after init.
3. **Bash and agent steps share rules.** `timeout_seconds`, `retry_count`, `failure_mode` (`fail`/`skip`/`pause`), `trigger_mode` (`auto`/`wait_for_trigger`/`wait_for_approval`), `notify_source`, `working_dir`, `env`. Identical surface for both — predictable.
4. **Inter-step data flow via named outputs.** A step writes to `PhaseExecution.result` (JSONB), and later step prompts/commands reference it via `{{steps.NAME.field}}` templating. No magic globals, no legacy `*_result` columns going forward (we keep writing them for back-compat for one release).
5. **Triggers are workflow config, not a separate system.** A `WorkflowTemplate.triggers[]` array declares "this workflow auto-runs when X happens." Webhook handlers + pollers + cron all funnel through one trigger-matching service.
6. **Steal myDash worktree pattern, don't copy myDash architecture.** Pure functions for naming, timestamp suffixes, idempotent cleanup. But our worktrees live on remote workspace servers, not a single-user host gateway.
7. **Frequent commits, conventional commit style, one logical change per commit.** Each task ends with a commit.
8. **TDD where the test is faster than the manual loop.** Always for core orchestration logic, models, and schemas. Pragmatic for UI polish.
9. **Don't break existing templates.** All 6 seeded templates (default, planner, hotfix, small-task, pr-review, fix-pr) must still run end-to-end at every commit on `main`.
10. **One PR per phase below.** A 30-task PR is unreviewable.

---

## Phase Roadmap

| # | Phase | Goal | Approx tasks | Ships separately? |
|---|-------|------|--------------|-------------------|
| 0 | Snapshot & ADR | Lock in the current state, draft superseding ADR | 3 | Yes — merge first |
| 1 | Generic step types (backend) | `bash` + `agent` step kinds, shared rules, output templating | 14 | Yes |
| 2 | Triggers as first-class | `WorkflowTemplate.triggers[]`, unified matcher | 8 | Yes |
| 3 | Frontend workflow builder | Compose steps, edit rules, preview triggers | 12 | Yes |
| 4 | Worktree workspace strategy | Optional worktree-per-run with timestamped naming | 7 | Yes |
| 5 | Deprecate legacy phases | Mark old phase modules as `kind: legacy_phase`, frontend stops special-casing | 6 | Yes |
| 6 | Docs + web overhaul | New README narrative, new ADR active, new web pages, blog post | 9 | Yes |

**Total ~59 tasks across 7 PRs.** Each phase below details its tasks.

---

## Phase 0 — Snapshot & ADR

### Task 0.1: Snapshot current state

**Files:**
- Create: `claudedocs/research/2026-05-23-current-pipeline-state.md`

**Step 1:** Synthesize the research already gathered (the parallel investigation that produced this plan) into a single file under `claudedocs/research/`. Include: every hardcoded phase-name list with file path + line, the existing `PhaseConfig` schema verbatim, the inter-phase data contracts (planning→coding via `planning_result.subtasks`, coding→reviewing via `coding_results.session_id`, approval→finalization via `pr_url`), the full list of webhook handlers and the label-match path, and the existing `WorkflowTemplate.label_rules` shape.

**Step 2:** Commit.

```bash
git add claudedocs/research/2026-05-23-current-pipeline-state.md
git commit -m "docs: snapshot current pipeline state for overhaul reference"
```

### Task 0.2: Draft superseding ADR

**Files:**
- Create: `claudedocs/decisions/007-composable-step-workflows.md`
- Modify: `claudedocs/decisions/005-multi-agent-pipeline.md` (status: Accepted → Superseded by 007)
- Modify: `claudedocs/INDEX.md` (add row for 007, update 005 row)

**Step 1:** Write ADR-007 following the format in `claudedocs/decisions/`. Required sections: Context (why 8 fixed phases is wrong now), Options Considered (A: keep 8 phases + better config UI; B: composable steps with legacy phases preserved as `kind: legacy_phase`; C: rewrite phase modules into generic step kinds), Decision (B), Rationale (additive, preserves existing templates, matches what agents actually do today), Consequences (frontend rewrite needed, docs rewrite needed, legacy phases become deprecated but functional).

**Step 2:** Flip ADR-005 status to `Superseded by ADR-007` with a one-line `> See [ADR-007](007-composable-step-workflows.md)` redirect at the top of the body. Do NOT delete content — keep history.

**Step 3:** Add ADR-007 row to `claudedocs/INDEX.md` and update ADR-005 summary to "superseded; see ADR-007."

**Step 4:** Commit.

```bash
git add claudedocs/decisions/007-composable-step-workflows.md claudedocs/decisions/005-multi-agent-pipeline.md claudedocs/INDEX.md
git commit -m "docs(adr): supersede ADR-005 with composable-step workflows (ADR-007)"
```

### Task 0.3: Open PR for Phase 0

```bash
git push -u origin feat/agentic-workflow-overhaul
gh pr create --draft --title "docs: agentic workflow overhaul — Phase 0 (snapshot + ADR)" --body "First of 7 PRs implementing the workflow overhaul. This one is doc-only. See claudedocs/plans/2026-05-23-agentic-workflow-overhaul.md."
```

---

## Phase 1 — Generic Step Types (Backend)

**Outcome:** A new `bash` step kind and a new `agent` step kind, both runnable from a workflow template's `phases[]` array alongside legacy phase names. Per-step rules (timeout, retry, failure_mode, env, working_dir) work for both. Output templating (`{{steps.NAME.field}}`) works in prompts and bash commands.

### Task 1.1: Add `kind` field to `PhaseConfig`

**Files:**
- Modify: `backend/schemas/workflows.py:16-29` (PhaseConfig)
- Test: `tests/unit/test_workflow_schemas.py` (create if missing)

**Step 1: Write failing test.**

```python
# tests/unit/test_workflow_schemas.py
from backend.schemas.workflows import PhaseConfig

def test_phase_config_defaults_kind_to_legacy_phase():
    cfg = PhaseConfig(phase_name="planning")
    assert cfg.kind == "legacy_phase"

def test_phase_config_accepts_bash_kind():
    cfg = PhaseConfig(phase_name="run-make-build", kind="bash", params={"command": "make build"})
    assert cfg.kind == "bash"

def test_phase_config_accepts_agent_kind():
    cfg = PhaseConfig(phase_name="fix-issue", kind="agent", params={"prompt": "Fix issue {{run.title}}"})
    assert cfg.kind == "agent"

def test_phase_config_rejects_unknown_kind():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PhaseConfig(phase_name="x", kind="not-a-kind")
```

**Step 2: Run test, confirm fail.**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_workflow_schemas.py -v
```

**Step 3: Add `kind: Literal["legacy_phase", "bash", "agent"] = "legacy_phase"` to `PhaseConfig` in `backend/schemas/workflows.py`.**

**Step 4: Re-run test, confirm pass. Run full schema/pipeline tests.**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_workflow_schemas.py tests/unit/test_pipeline.py tests/unit/test_phase_config_merge.py -v
```

**Step 5: Commit.**

```bash
git add backend/schemas/workflows.py tests/unit/test_workflow_schemas.py
git commit -m "feat(workflows): add kind discriminator to PhaseConfig (legacy_phase|bash|agent)"
```

### Task 1.2: Persist `kind` in `PhaseExecution.phase_config` (no schema change needed)

**Files:**
- Modify: `backend/repositories/phase_execution_repo.py` (verify create_for_run copies `kind` through)
- Test: `tests/unit/test_phase_execution_repo.py`

**Step 1: Write test asserting `kind` survives the round-trip from template → PhaseExecution.phase_config['kind']. Run, confirm fail (or pass if repo already passes the whole dict through).**

**Step 2: If repo strips unknown fields, fix to pass through. Re-run.**

**Step 3: Commit.**

```bash
git add backend/repositories/phase_execution_repo.py tests/unit/test_phase_execution_repo.py
git commit -m "feat(workflows): preserve step kind in PhaseExecution.phase_config"
```

### Task 1.3: Create `BashStepRunner`

**Files:**
- Create: `backend/worker/steps/__init__.py`
- Create: `backend/worker/steps/bash_step.py`
- Create: `tests/unit/test_bash_step.py`

**Step 1: Write failing test for happy path, timeout path, failure_mode='skip' path, and template substitution `{{steps.NAME.field}}` rendering.**

```python
# tests/unit/test_bash_step.py
import pytest
from unittest.mock import AsyncMock
from backend.worker.steps.bash_step import run_bash_step

@pytest.mark.asyncio
async def test_runs_command_and_captures_output(mock_services, make_task_run, db_session):
    run = make_task_run()
    db_session.add(run); await db_session.commit()
    executor = AsyncMock()
    executor.run_command = AsyncMock(return_value=("hello\n", "", 0))
    phase_config = {"kind": "bash", "params": {"command": "echo hello"}}
    result = await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)
    assert result["exit_code"] == 0
    assert result["stdout"] == "hello\n"

@pytest.mark.asyncio
async def test_substitutes_previous_step_outputs(mock_services, make_task_run, db_session):
    run = make_task_run()
    db_session.add(run); await db_session.commit()
    # Seed a prior PhaseExecution with result
    from backend.models import PhaseExecution
    prior = PhaseExecution(
        run_id=run.id, phase_name="build", order_index=1, status="completed",
        result={"artifact_path": "/tmp/build.tar"}
    )
    db_session.add(prior); await db_session.commit()
    executor = AsyncMock()
    executor.run_command = AsyncMock(return_value=("ok", "", 0))
    phase_config = {"kind": "bash", "params": {"command": "deploy {{steps.build.artifact_path}}"}}
    await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)
    executor.run_command.assert_awaited_once()
    assert "deploy /tmp/build.tar" in executor.run_command.call_args[0][0]

@pytest.mark.asyncio
async def test_raises_on_nonzero_when_failure_mode_fail(mock_services, make_task_run, db_session):
    run = make_task_run()
    db_session.add(run); await db_session.commit()
    executor = AsyncMock()
    executor.run_command = AsyncMock(return_value=("", "boom", 1))
    phase_config = {"kind": "bash", "params": {"command": "false"}, "failure_mode": "fail"}
    with pytest.raises(Exception):
        await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)

@pytest.mark.asyncio
async def test_returns_result_when_failure_mode_skip(mock_services, make_task_run, db_session):
    run = make_task_run()
    db_session.add(run); await db_session.commit()
    executor = AsyncMock()
    executor.run_command = AsyncMock(return_value=("", "boom", 1))
    phase_config = {"kind": "bash", "params": {"command": "false"}, "failure_mode": "skip"}
    result = await run_bash_step(run, db_session, mock_services, phase_config, executor=executor)
    assert result["exit_code"] == 1
    assert result["skipped"] is True
```

**Step 2: Run tests, confirm 4 failures.**

**Step 3: Implement `run_bash_step` in `backend/worker/steps/bash_step.py`.**

```python
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

"""Generic bash step runner — executes a shell command on the workspace."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import TaskRun
from backend.services.container import ServiceContainer
from backend.worker.phases._helpers import get_ssh_for_run
from backend.worker.steps.templating import render

# Defaults
DEFAULT_TIMEOUT = 600


async def run_bash_step(
    task_run: TaskRun,
    session: AsyncSession,
    services: ServiceContainer,
    phase_config: dict[str, Any],
    *,
    executor=None,
) -> dict[str, Any]:
    params = phase_config.get("params", {})
    raw_cmd = params["command"]
    cmd = await render(raw_cmd, task_run, session)
    timeout = phase_config.get("timeout_seconds") or DEFAULT_TIMEOUT
    failure_mode = phase_config.get("failure_mode", "fail")

    if executor is None:
        executor = await get_ssh_for_run(task_run, session)

    stdout, stderr, rc = await executor.run_command(cmd, timeout=timeout)
    result = {"command": cmd, "stdout": stdout, "stderr": stderr, "exit_code": rc}
    if rc != 0:
        if failure_mode == "skip":
            result["skipped"] = True
            return result
        raise RuntimeError(f"bash step failed (rc={rc}): {stderr or stdout}")
    return result
```

**Step 4: Implement minimal `render()` in `backend/worker/steps/templating.py` (handles `{{steps.NAME.field}}` and `{{run.title}}` / `{{run.description}}` / `{{run.task_id}}` only — no full Jinja).**

**Step 5: Re-run tests, confirm pass.**

**Step 6: Commit.**

```bash
git add backend/worker/steps/ tests/unit/test_bash_step.py
git commit -m "feat(workflows): generic bash step runner with output templating"
```

### Task 1.4: Create `AgentStepRunner`

**Files:**
- Create: `backend/worker/steps/agent_step.py`
- Create: `tests/unit/test_agent_step.py`

**Step 1: Write failing test.** Parameters under test: `role` (defaults to "coder"), `prompt` (template-rendered), `agent_override`, `cli_flags`, `environment_vars`, `session_id` (optional, for resume), `new_session` (boolean), output captured to `result.response` and `result.session_id`.

**Step 2: Implement `run_agent_step` that calls `services.role_resolver.resolve(...)` → `adapter.generate(prompt, ...)` and writes the response. Mirror the structure of `coding.py:137-148` but generic (no subtask iteration, no consolidated/batch branches).**

**Step 3: Commit.**

```bash
git add backend/worker/steps/agent_step.py tests/unit/test_agent_step.py
git commit -m "feat(workflows): generic agent step runner using RoleResolver"
```

### Task 1.5: Wire step kinds into the pipeline executor

**Files:**
- Modify: `backend/worker/pipeline.py` (the loop in `execute_pipeline` that resolves phase module by name)
- Test: `tests/unit/test_pipeline.py` (add 2 cases)

**Step 1: Add failing tests asserting that a workflow with a `bash` step + a legacy `coding` phase + an `agent` step runs all three in order.**

**Step 2: Modify the dispatch in `execute_pipeline`** — when `phase_config['kind'] == 'bash'` call `run_bash_step`, when `kind == 'agent'` call `run_agent_step`, when `kind == 'legacy_phase'` (or missing) fall back to current registry lookup by `phase_name`.

**Step 3: Confirm all existing pipeline tests still pass.**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/unit/test_pipeline.py -v
```

**Step 4: Commit.**

```bash
git add backend/worker/pipeline.py tests/unit/test_pipeline.py
git commit -m "feat(workflows): dispatch bash/agent steps from pipeline executor"
```

### Task 1.6: Seed a new `bash-and-claude` example template

**Files:**
- Modify: `backend/seed/workflow_templates.py`
- Test: `tests/unit/test_seed_workflow_templates.py`

**Step 1: Add a new system template `example-composable` with `workspace_setup → init → bash(make build) → agent(role=coder, prompt="Run tests and report") → bash(deploy if tests pass)` to demonstrate the new shape.**

**Step 2: Test confirms it seeds and matches no labels by default.**

**Step 3: Commit.**

```bash
git add backend/seed/workflow_templates.py tests/unit/test_seed_workflow_templates.py
git commit -m "feat(workflows): seed example-composable template (bash + agent atoms)"
```

### Task 1.7: Migration adding a `step_outputs` JSONB column to TaskRun (for templating future-proofing)

**Optional — defer to v2 unless templating tests show we need it. PhaseExecution.result already serves this.** Skip in v1 to avoid scope creep.

### Task 1.8: Integration test — end-to-end workflow with bash + agent steps

**Files:**
- Create: `tests/integration/test_composable_workflow.py`

**Step 1: Write integration test: POST a workflow_template with the composable shape, POST a run, mock adapters and SSH, drive the pipeline, assert all three steps ran in order and result JSON shape.**

**Step 2: Commit.**

```bash
git add tests/integration/test_composable_workflow.py
git commit -m "test(workflows): end-to-end composable workflow integration"
```

### Task 1.9: API — `GET /step-kinds` endpoint

**Files:**
- Modify: `backend/api/workflow_templates.py`
- Test: `tests/integration/test_workflow_templates_api.py`

**Step 1: Add `GET /step-kinds` returning `[{kind: "bash", params_schema: {...}}, {kind: "agent", params_schema: {...}}, {kind: "legacy_phase", values: [...discovered phase names]}]`. Test the shape.**

**Step 2: Commit.**

```bash
git add backend/api/workflow_templates.py tests/integration/test_workflow_templates_api.py
git commit -m "feat(api): expose available step kinds for workflow builder"
```

### Task 1.10: Backend lint / type / full suite

```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/ --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/ tests/
docker compose -f docker-compose.dev.yml exec backend pyright backend/
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -v
```

Fix anything that fails. Commit.

### Task 1.11: Open Phase 1 PR

```bash
git push
gh pr create --title "feat(workflows): composable step types (bash + agent)" --body "Phase 1 of 7 in the agentic workflow overhaul. Adds two new step kinds runnable from any workflow template. Legacy phases unchanged. See claudedocs/plans/2026-05-23-agentic-workflow-overhaul.md."
```

**Wait for review + merge before starting Phase 2.**

---

## Phase 2 — Triggers as First-Class

**Outcome:** A `WorkflowTemplate.triggers[]` field declares which external events auto-fire the workflow. Unified `TriggerMatcher` service replaces ad-hoc per-webhook template lookups.

### Task 2.1: Migration — add `triggers` JSONB column to `workflow_templates`

**Files:**
- Create: `alembic/versions/037_workflow_template_triggers.py`
- Modify: `backend/models/workflows.py` (add `triggers = Column(JSONB, nullable=False, server_default="[]")`)
- Modify: `backend/schemas/workflows.py` (add `WorkflowTriggerRule` and `WorkflowTemplate.triggers`)

**Step 1: Write the migration. Run `alembic upgrade head` in docker. Confirm column exists via `\d workflow_templates`.**

**Step 2: Update model + schema. Tests for round-trip.**

**Step 3: Commit.**

```bash
git add alembic/versions/037_workflow_template_triggers.py backend/models/workflows.py backend/schemas/workflows.py tests/
git commit -m "feat(workflows): add triggers field to WorkflowTemplate"
```

### Task 2.2: Define trigger types

`WorkflowTriggerRule` is a discriminated union:
- `{type: "label", source: "github"|"gitea"|"gitlab"|"plane"|"notion"|"any", match_all: [...], match_any: [...]}` (replaces existing `label_rules`)
- `{type: "issue_event", source: "...", action: "opened"|"labeled"|"commented", filter: {...}}`
- `{type: "pr_event", source: "...", action: "opened"|"review_requested"|...}`
- `{type: "schedule", cron: "0 9 * * *"}`
- `{type: "manual"}` (always available, baseline)

Write Pydantic models with discriminated union via `Annotated[Union[...], Field(discriminator="type")]`. Test rejection of unknown types.

### Task 2.3: `TriggerMatcher` service

**Files:**
- Create: `backend/services/triggers/matcher.py`
- Create: `tests/unit/test_trigger_matcher.py`

**Step 1: Write failing tests:** given an event payload + a list of templates, returns the first matching template (priority by `is_default` last, `is_system` last, manual updated_at most-recent first).

**Step 2: Implement.**

**Step 3: Commit.**

### Task 2.4: Migrate existing `label_rules` to `triggers[{type:"label"}]`

**Files:**
- Modify: `alembic/versions/037_workflow_template_triggers.py` (data migration)
- Modify: `backend/seed/workflow_templates.py`

Make the migration COPY existing `label_rules` rows into `triggers` as `{type: "label", source: "any", match_all: [...], match_any: [...]}`. Drop the column in a later release (NOT this one — write-through both for one version).

### Task 2.5: Webhook handlers funnel through `TriggerMatcher`

**Files:**
- Modify: `backend/api/webhooks.py` (each handler builds an event payload, asks matcher, creates run)
- Modify: `backend/worker/pipeline.py:97` (`_resolve_workflow_phases` keeps label fallback for back-compat but warns)
- Test: `tests/integration/test_webhooks_api.py`

### Task 2.6: Schedule trigger via existing `platform_crons` infra

Lightweight — a new `ScheduleTriggerScheduler` polls `WorkflowTemplate` rows with `triggers[?type=="schedule"]`, evaluates cron, dispatches a run.

### Task 2.7: API — `POST /workflow-templates/{id}/dry-run` to test triggers

Accepts a fake event payload, returns which templates match. Useful for the frontend trigger editor.

### Task 2.8: Open Phase 2 PR

---

## Phase 3 — Frontend Workflow Builder

**Outcome:** A new page (or rewrite of `WorkflowTemplates.tsx`) where the user composes a workflow as an ordered list of steps. Each step shows a kind selector (`bash`/`agent`/`legacy_phase`), kind-specific params, and shared rules. Triggers tab next to the steps tab. Generic step-result viewer in `RunDetail` so adding a new step kind doesn't require frontend changes.

### Task 3.1: Frontend types

**Files:** `frontend/src/types/workflows.ts` — extend `PhaseConfig` with `kind`, add `WorkflowTriggerRule` union, add `StepKindDescriptor`.

### Task 3.2: `useStepKinds()` query hook — fetches `GET /step-kinds`.

### Task 3.3: `StepEditor` component

Renders the right param form based on `kind`. For `bash`: command textarea, working_dir, env editor. For `agent`: role select, prompt textarea with `{{steps.NAME.field}}` autocomplete from prior steps in the list, agent_override, cli_flags, env. For `legacy_phase`: name dropdown from the discovered list (current behavior).

### Task 3.4: `StepListEditor` — drag-to-reorder, add/remove, duplicate.

### Task 3.5: `TriggerEditor` — list of `WorkflowTriggerRule` with kind selector.

### Task 3.6: Rewrite `WorkflowTemplates.tsx` page

Tabs: Steps | Triggers | Settings (name/description/is_default). Remove `phase.phase_name === "coding"` special-case (Task 5.x will fully kill it).

### Task 3.7: `NewRun.tsx` cleanup

Remove hardcoded `PHASES_WITH_AGENTS` (`NewRun.tsx:19-26`). Pull from the selected template's `phases[]` after fetching template detail.

### Task 3.8: `RunDetail.tsx` — generic step result viewer

Replace `phaseName === "coding"` / `=== "reviewing"` branches at `RunDetail.tsx:325-339` with a single `GenericStepResult({phaseExecution})` that handles bash (terminal-style stdout+stderr+exit_code+command) and agent (rendered response) by `kind`, falling back to current CollapsibleJSON for legacy_phase.

### Task 3.9: `PhaseTimeline.tsx` — remove hardcoded `PHASES` list

Render from actual `phase_executions` only. No fallback constant.

### Task 3.10: Frontend tests for new components.

### Task 3.11: Frontend lint + type + tests.

```bash
docker compose -f docker-compose.dev.yml exec frontend npm run lint
docker compose -f docker-compose.dev.yml exec frontend npm run build  # tsc strict
docker compose -f docker-compose.dev.yml exec frontend npm test
```

### Task 3.12: Open Phase 3 PR

---

## Phase 4 — Worktree Workspace Strategy

**Outcome:** A new `workspace_config.strategy = "worktree"` option that creates a git worktree per run on the workspace server, with timestamped naming stolen from myDash. Default remains current "shared clone." Opt-in per project or per template.

### Task 4.1: Pure functions — `make_worktree_paths`

**Files:**
- Create: `backend/services/workspace/worktree.py`
- Create: `tests/unit/test_worktree.py`

Steal exactly the function from `myDash/backend/host-gateway/app/fix_issue.py:23-39`. Adapt for our naming (`branch = "run/{run_id}-{ts}"`, `worktree = "{project_root}/.worktrees/run-{run_id}-{ts}"`). Pure, no IO, fully unit-testable.

### Task 4.2: `WorktreeManager` service — create/remove via `CommandExecutor`

Idempotent. `chown` to worker user (matches `ensure_agent_ready` pattern in `_helpers.py`). Mirror `myDash/fix_issue.py:112-199`.

### Task 4.3: Wire into `workspace_setup` phase

When `phase_config.params.workspace_strategy == "worktree"`, after cloning, create the worktree and set `task_run.workspace_path` to the worktree dir.

### Task 4.4: Cleanup on finalization

When workspace strategy is worktree, `finalization.py` calls `WorktreeManager.remove`. Skip if finalization is configured `keep_workspace: true` (debugging).

### Task 4.5: Cleanup orphans cron

A scheduled task removes `.worktrees/run-*` dirs older than N days whose corresponding TaskRun is in a terminal state.

### Task 4.6: Tests + integration test.

### Task 4.7: Open Phase 4 PR

---

## Phase 5 — Deprecate Legacy Phases

**Outcome:** Legacy phase modules (`planning.py`, `coding.py`, etc.) still work but are exposed as `kind: legacy_phase` step types. Frontend stops special-casing phase names. `_LEGACY_RESULT_MAP` removed (read path keeps fallback for one release).

### Task 5.1: Mark legacy phase modules

Add `PHASE_META = {"kind": "legacy_phase", "deprecated_in": "0.5.0"}` to each of: `planning.py`, `coding.py`, `testing.py`, `reviewing.py`, `approval.py`, `finalization.py`, `pr_fetch.py`, `task_creation.py`, `agent_loop.py`. Keep `workspace_setup.py` and `init_phase.py` as `kind: builtin`.

### Task 5.2: Remove `_LEGACY_RESULT_MAP` write path

Stop writing `task_run.planning_result` etc. on phase completion. Read path keeps the legacy columns for one release (mark for removal in 0.6.0).

### Task 5.3: Frontend — drop phase-name special cases everywhere

Verify generic `GenericStepResult` from Task 3.8 covers everything. Remove `coding`/`reviewing` branches. Remove `PHASES_WITH_AGENTS` (already done in 3.7). Remove `PHASES` fallback in `PhaseTimeline` (already done in 3.9).

### Task 5.4: Update seeded `default` template description

Its name stays `default` and its phases list stays the same (8 phases of `kind: legacy_phase`), but its `description` is updated: "Legacy 8-phase pipeline. New workflows should use composable steps."

### Task 5.5: Bump version to 0.5.0 in changelog

### Task 5.6: Open Phase 5 PR

---

## Phase 6 — Docs + Web Overhaul

**Outcome:** README, in-repo docs, and the www marketing site reflect the new model. Old "8-phase pipeline" narrative is fully replaced with "composable steps + triggers" framing, with the legacy pipeline mentioned as a backward-compatible template.

### Task 6.1: Rewrite `README.md`

**Files:** `/home/domas/projects/autodev/README.md`

Sections to rewrite (per the research report):
- Tagline (line 7) — drop "8-phase pipeline" wording
- "What makes AgenticKode different" — replace pipeline bullet with "composable agent + bash steps with triggers"
- "How It Works" table (lines 55-58)
- ASCII pipeline diagram (lines 62-69) — replace with a worker–trigger–step diagram
- "The 8-Phase Pipeline" table (lines 71-84) — replace with "Step Kinds" table (`bash` | `agent` | `legacy_phase`) and "Triggers" subsection
- Architecture ASCII art (line 303)
- Project Structure comment (line 424)
- Docs link table (line 448) — point to new step guide

### Task 6.2: Replace `docs/WORKER_PIPELINE.md`

This is the 1558-line technical reference. Move to `docs/legacy-pipeline.md` with a redirect note. Write a fresh `docs/workflows.md` covering: step kinds, triggers, templating, examples, migration from legacy templates.

### Task 6.3: Update `claudedocs/INDEX.md`

Add row for new `docs/workflows.md`. Update existing pipeline row to "(legacy — see workflows.md)."

### Task 6.4: Rewrite `www/content/docs/guides/worker-pipeline.md`

Rename file to `workflows.md`. Add redirect in old slug.

### Task 6.5: Rewrite `www/content/blog/understanding-8-phase-pipeline.md`

New slug `composable-agentic-workflows`. Frame: "we started with 8 phases, here's what we learned, here's the new model." Honest migration story.

### Task 6.6: Update `www/components/landing/PipelineSection.vue`

Replace `pipelinePhases` array (lines 23-32) with example workflow nodes (`workspace_setup → init → [bash: clone deps] → [agent: planner] → [agent: coder] → [bash: tests] → [agent: reviewer] → [approval]`). Update tab labels from `'8-Phase'` / `'Pipeline'` to `'Workflows'` / `'Composable Steps'`. Remove the `length === 8` grid special-case.

### Task 6.7: Update other www files

- `www/components/landing/HeroSection.vue` — terminal animation
- `www/components/landing/ModesSection.vue` — description copy
- `www/components/landing/NavBar.vue` — anchor label
- `www/content/docs/index.md` — link updates
- `www/content/docs/quick-start.md` — lines 71, 109
- `www/content/blog/introducing-agentickode.md` — lines 3, 29, 37
- `www/content/docs/guides/autonomous-mode.md` — table row line 43
- `www/pages/index.vue` — SEO description lines 18, 39

### Task 6.8: New blog post — "Why we replaced our 8-phase pipeline"

`www/content/blog/composable-agentic-workflows.md`. Length ~1200 words. Cover: original problem (every agent does everything anyway → fixed phases are LARP), data flow rethink, triggers as first-class, worktree-per-run inspired by myDash, migration story for existing users.

### Task 6.9: Open Phase 6 PR + tag release

```bash
git tag v0.5.0
git push --tags
gh release create v0.5.0 --title "v0.5.0 — Composable agentic workflows" --notes "$(cat CHANGELOG.md | sed -n '/## 0.5.0/,/## /p')"
```

---

## Open Questions (resolve before starting any task)

1. **Backward-compat horizon.** Do we keep legacy `*_result` TaskRun columns for one release (proposed) or two? Affects external integrations reading those fields.
2. **Trigger storage.** Confirm `WorkflowTemplate.triggers` JSONB vs a separate `workflow_triggers` table. JSONB is faster to ship and matches how `phases` is stored, but querying "which workflows match this event" is O(N) over templates. Pick before Task 2.1.
3. **Templating engine.** Hand-rolled `{{steps.NAME.field}}` (proposed, ~50 lines) or pull in `jinja2`? Hand-rolled is safer (no untrusted exec); Jinja unlocks loops/conditionals later but is overkill for v1.
4. **Worktree on remote servers.** myDash's host-gateway runs git as the host user via `setpriv`. We already SSH as the worker user — confirm `git worktree add` works under that user against the existing clone. May need ownership fix-ups already covered by `ensure_agent_ready`.
5. **Frontend rewrite scope.** Replace `WorkflowTemplates.tsx` in-place (proposed) or build new `Workflows.tsx` alongside it and deprecate the old? In-place is cleaner; alongside is safer if users have it open mid-rollout.

Resolve these inline in the relevant ADR / first task of each phase.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Big PRs become unreviewable | One PR per phase above (7 PRs total) |
| Breaking existing templates mid-rollout | Legacy phase modules stay registered; `kind: legacy_phase` is the default; all 6 seeded templates run on every merge to main (CI gate) |
| Frontend desync from backend during phased rollout | Schema-shared types (generate `frontend/src/types/workflows.ts` from Pydantic models — or hand-mirror with a test asserting parity) |
| Cost tracking breaks if step kinds change attribution | `AgentInvocation.phase_name` is text; bash steps don't invoke agents so they have no cost attribution — that's correct behavior |
| Worktree disk fill on remote servers | Phase 4 ships cleanup cron (Task 4.5); worktree storage opt-in per project |
| Web repo published mid-overhaul shows stale 8-phase narrative | Phase 6 ships docs in lockstep with v0.5.0 release tag; nothing on the www site changes until then |
| Migration 037 + future schema changes need to coordinate with prod data | Each migration tested in dev DB first; data migrations include downgrade path |

---

## Definition of Done

- All 7 PRs merged to main
- v0.5.0 tagged + released
- README, `docs/workflows.md`, `claudedocs/decisions/007-composable-step-workflows.md`, and all www pages reflect the new model
- 6 seeded templates run green end-to-end in integration tests
- One new system template (`example-composable`) demonstrates the new shape
- No frontend page references hardcoded phase names except for legacy compatibility rendering
- `legacy_phase` kind documented and supported indefinitely; new development uses `bash` + `agent`

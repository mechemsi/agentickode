---
title: Flow prompts — Phase 1 (additive, flag-gated)
status: implemented
date: 2026-06-09
related:
  - claudedocs/decisions/009-flow-prompts.md
  - claudedocs/plans/2026-06-08-workflows-to-flow-prompts.md
---

# Flow prompts — Phase 1

First phase of ADR-009. **Purely additive and OFF by default** (`FLOW_PROMPTS_ENABLED=false`):
nothing is removed, workflow templates run exactly as before. Lays the data layer + the
slimmed single-agent-call executor behind a feature flag + run binding.

## What was built

| File | Purpose |
|------|---------|
| `backend/models/flow_prompts.py` | `FlowPrompt` model (`flow_prompts`): name, flow_type, prompt, agent, agent_mode, extra_data_sources, triggers, is_system, enabled |
| `backend/models/runs.py` | `task_runs.flow_prompt_id` (nullable FK) |
| `alembic/versions/043_flow_prompts.py` + `backend/main.py` | migration 042→043 (table + FK) + idempotent runtime guard |
| `backend/repositories/flow_prompt_repo.py` | `FlowPromptRepository` (get_by_id/name/flow_type, create) |
| `backend/worker/flow/data_sources.py` | per-flow-type fixed data sources (`FLOW_TYPE_SOURCES`) + per-prompt extras; `fetch_flow_data` gathers, skips unknown/failed |
| `backend/worker/flow/executor.py` | `execute_flow_prompt`: setup (task-mode) → fetch data → **single `run_agent_step`** → result into `coding_results` → finalization |
| `backend/worker/pipeline.py` | fork at top of `execute_pipeline`: `if flow_prompts_enabled and run.flow_prompt_id → execute_flow_prompt` |
| `backend/config.py` | `flow_prompts_enabled: bool = False` |
| `backend/seed/flow_prompts.py` | seeds default `implement` (task) + `pr-review` (generate) flow prompts (idempotent) |
| `tests/unit/test_flow_prompts.py` | repo, `sources_for` dedup, `fetch_flow_data`, `_compose_prompt` (9 tests) |

## How it works (when enabled)
A run bound to a `flow_prompt_id` skips the phase-execution pipeline: it runs builtin
`workspace_setup`+`init` (task mode only), fetches the flow type's fixed data sources plus any
per-prompt extras, composes the prompt + a context block, makes **one** agent call via
`run_agent_step`, stores the response on `task_runs.coding_results`, then runs `finalization`.

Decisions realised (ADR-009): single agent call; result on `coding_results` (no per-step
`phase_executions`); data fixed-per-type + declarable-per-prompt. Comparison mode and the
template/`phase_executions` removals come in Phases 4–5.

## Verification
- Backend: 9 new unit tests; full suite green; migration 043 applies (042→043); ruff + pyright clean.

## Next phases (ADR-009)
2. Port PR-review to the `pr-review` flow prompt; re-point poller/webhooks; verify parity.
3. Default new runs to flow prompts; deprecate template creation.
4. Remove WorkflowTemplates UI + comparison mode.
5. Remove `WorkflowTemplate` API/model + `phase_executions`; drop tables (irreversible).

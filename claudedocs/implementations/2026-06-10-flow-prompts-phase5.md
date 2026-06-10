---
title: Flow prompts — Phase 5 (remove the workflow-template engine)
status: implemented
date: 2026-06-10
related:
  - claudedocs/decisions/009-flow-prompts.md
  - claudedocs/plans/2026-06-08-workflows-to-flow-prompts.md
  - claudedocs/implementations/2026-06-09-flow-prompts-phase3-default.md
---

# Flow Prompts — Phase 5

## What Was Built

The final ADR-009 phase. Every run is now a **single flow-prompt agent call**; the
legacy multi-step `WorkflowTemplate` / `PhaseExecution` dispatch engine was removed
entirely (`mechemsi/agentickode#41`). Completes the Notion task *"Replace server
workflows with flow prompts"*.

**Irreversible:** dropped `workflow_templates` + `phase_executions` and the
`task_runs.workflow_template_id` / `agent_invocations.phase_execution_id` FK columns.
Historical per-step records + template linkage are lost (accepted per ADR-009 OQ-1/OQ-7).

## Key Files

| File | Change |
|------|--------|
| `backend/worker/pipeline.py` | `execute_pipeline` resolves the run's flow prompt (`pr_review` for review runs, `implement` otherwise) and delegates to the flow executor. Phase loop / `_resolve_workflow_phases` / `_ensure_phase_executions` / autonomous-sequence dispatch removed. |
| `backend/config.py` | Removed `flow_prompts_enabled` — flow prompts are unconditional. |
| `backend/models/runs.py` | Removed `PhaseExecution`; dropped `task_runs.workflow_template_id` + `agent_invocations.phase_execution_id`. |
| `backend/models/webhooks.py` | New home for `WebhookCallback` (was in the deleted `models/workflows.py`). |
| `backend/services/triggers/matcher.py`, `worker/schedule_trigger_scheduler.py` | Repointed from `WorkflowTemplate` to `FlowPrompt.triggers`. |
| `backend/api/_pr_webhook_helpers.py`, `webhooks_pr.py`, `services/task_source_polling/pr_review_poller.py` | PR-review gates on the `ai-review` label and binds the `pr_review` flow prompt (no template lookup). |
| `backend/services/backup/entity_registry.py` | Exports `flow_prompts` instead of `workflow_templates`. |
| `backend/api/runs_phases.py` | Trimmed to the agent-invocation (cost) endpoints; dropped `/phases`, `/advance`, `/plan-review`. |
| `alembic/versions/044_drop_workflow_templates.py` + `backend/main.py` | Drop the tables/columns (`IF EXISTS`, FK columns first). |
| `frontend/src/types/runs.ts`, `pages/RunDetail.tsx`, `components/runs/PhaseTimeline.tsx` | `workflow_template_id` → `flow_prompt_id`; removed `PhaseExecution` + `phase_executions`; PhaseTimeline shows the current step only; RunDetail simplified. |

**Removed modules:** `workflow_templates` API/repo/seed, `phase_execution_repo`, `bash_step`,
the dead legacy phase modules (planning/coding/testing/reviewing/approval/agent_loop/task_creation
+ `_coding_*`/`_reviewing_loop`/`_followup_handler`/`_context_builder`/`_review_helpers`/`_memory_hook`),
`{{steps.*}}` templating, dead `_helpers` phase-config functions, and the frontend
`GenericStepResult` + `PlanReviewPanel`.

**Kept (flow path):** `workspace_setup`, `init`, `finalization`, `pr_fetch`, `agent_step`.

## How It Works

```
run created
  → resolve flow prompt (pr_review if review_mode else implement)
  → execute_flow_prompt:
       workspace_setup + init (task mode only)
       → fetch the flow's data (repo/issue or PR diff)
       → ONE agent call (run_task, or generate for diff-only)
       → finalization (cleanup; post PR comment for review runs)
```

## Notes / Follow-ups

- **102 files, +415 / −10,865.** Backend 1167 + frontend 250 tests green; migration verified
  on dev + devbox.
- **Devbox is now flow-prompts-only** but has no claude auth → claude `implement` runs there
  fail until claude auth + a durable non-root worker are provisioned. PR-review/implement via
  other agents work.
- The legacy result-mirror columns (`planning_result`, `test_results`, …) on `task_runs` remain
  for back-compat; the flow executor writes its outcome to `coding_results` / `review_result`.

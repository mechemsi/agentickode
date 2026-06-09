---
title: Flow prompts — Phase 3 (default new runs to flow prompts)
status: implemented
date: 2026-06-09
related:
  - claudedocs/decisions/009-flow-prompts.md
  - claudedocs/implementations/2026-06-09-flow-prompts-phase2-pr-review.md
---

# Flow prompts — Phase 3 (default + deprecate templates)

Makes flow prompts the **default** execution path and deprecates template creation —
still **gated behind `FLOW_PROMPTS_ENABLED`** (off → unchanged template pipeline).

## What was built

| File | Change |
|------|--------|
| `backend/worker/pipeline.py` | When the flag is on and a run has **no** `flow_prompt_id`, default it to the `implement` flow prompt (resolved by `get_by_flow_type`), persist, and execute via `execute_flow_prompt`. Phase 1/2 bindings (e.g. PR-review) still take precedence. |
| `backend/api/workflow_templates.py` | `create_workflow_template` logs a deprecation warning (ADR-009) when the flag is on — creation still works for transition. |
| `tests/unit/test_flow_prompts.py` | seed creates resolvable `implement` (task) + `pr-review` (generate) prompts; seed is idempotent. |

## Behavior (flag on)
- A normal `ai_task` run with no explicit flow prompt → executes via the **`implement`** flow
  prompt (single agent call: setup → fetch repo/issue context → one `run_task` agent call →
  `coding_results` → finalization), replacing the multi-phase pipeline.
- PR-review runs keep their `pr_review` binding from Phase 2.
- Flag off → every run uses the workflow-template pipeline exactly as before (no change).

## Verification
- Backend: 14 flow/PR-review tests pass; full suite green; ruff + pyright clean.

## Next (ADR-009)
Phase 4: remove the WorkflowTemplates UI + comparison mode. Phase 5: remove
`WorkflowTemplate` API/model + `phase_executions`; drop tables (irreversible).

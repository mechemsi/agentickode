---
title: Flow prompts — Phase 2 (PR-review on a flow prompt)
status: implemented
date: 2026-06-09
related:
  - claudedocs/decisions/009-flow-prompts.md
  - claudedocs/implementations/2026-06-09-flow-prompts-phase1.md
  - claudedocs/implementations/2026-06-05-pr-review-poller.md
---

# Flow prompts — Phase 2 (PR-review)

Ports the PR-review path onto the `pr-review` flow prompt, **behind `FLOW_PROMPTS_ENABLED`**.
When the flag is off, PR-review runs exactly as before (workflow template); when on, the same
runs also bind to the flow prompt and execute via the single-agent-call path.

## What was built

| File | Change |
|------|--------|
| `backend/api/_pr_webhook_helpers.py` | `build_pr_review_run` takes optional `flow_prompt_id`; new `resolve_pr_review_flow_prompt_id(db)` returns the `pr_review` flow prompt id **only when the flag is on** (else None). The webhook handler passes it. |
| `backend/services/task_source_polling/pr_review_poller.py` | resolves the flow prompt id once per poll and passes it to `build_pr_review_run`. |
| `backend/worker/flow/executor.py` | for `flow_type == "pr_review"`, sets `task_run.review_result = {summary: <agent response>, ...}` so `finalization` posts the comment + flips the `ai-review → ai-reviewed` label (parity with the template path). |
| `tests/unit/test_pr_review_flow_prompt.py` | flag-gating of `resolve_pr_review_flow_prompt_id` (off→None, on+no-flow→None, on+flow→id). |

## Parity mechanism
A flow-bound PR-review run (`flow_type=pr_review`, `agent_mode=generate`, fixed source `pr_diff`):
1. pipeline fork → `execute_flow_prompt` (flag on + `flow_prompt_id`).
2. `pr_diff` data source runs the existing `pr_fetch` (diff + comments into `coding_results`),
   composed into the prompt context.
3. single `generate` agent call (no workspace checkout).
4. response → `review_result` → `finalization` posts the PR comment + flips the label.
   `task_source_meta.review_mode == "comment"` (set by `build_pr_review_run`) keeps it
   comment-only (never pushes) — same guard as the template path.

Runs still carry `workflow_template_id` too, so toggling the flag off cleanly reverts to the
template path for new runs.

## Verification
- Backend: new flag-gating tests + existing PR-review suites (poller/webhooks/pipeline) pass;
  full suite green; ruff + pyright clean.

## Next (ADR-009)
Phase 3: default new runs to flow prompts; deprecate template creation. Phases 4–5: remove
templates UI + comparison, then drop `workflow_templates` + `phase_executions` (irreversible).

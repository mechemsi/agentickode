---
title: Flow prompts — live validation + two fixes
status: implemented
date: 2026-06-09
related:
  - claudedocs/decisions/009-flow-prompts.md
  - claudedocs/implementations/2026-06-09-flow-prompts-phase2-pr-review.md
  - claudedocs/implementations/2026-06-09-flow-prompts-phase3-default.md
---

# Flow prompts — live validation (before Phases 4–5)

Enabled `FLOW_PROMPTS_ENABLED=true` on the **local** instance (the only claude-authenticated one;
the devbox has claude installed but **no credentials**) and ran a real PR-review of
`mechemsi/agentickode#31` via the CI endpoint. This surfaced and fixed two real bugs and proved
the flow engine end-to-end.

## Bugs found + fixed

1. **CI endpoint didn't bind the flow prompt** (`backend/api/webhooks_pr.py`). Phase 2 wired the
   webhook + poller but missed the `trigger_pr_review` CI endpoint, so its run had no
   `flow_prompt_id` → Phase 3's default mis-routed it to the **implement** flow (task mode →
   `workspace_setup` failure). Fix: the CI endpoint now passes `resolve_pr_review_flow_prompt_id(db)`.
2. **Executor didn't resolve a workspace server** (`backend/worker/flow/executor.py`). Legacy
   phases resolve the server via `get_workspace_server_id` (falls back to the project's assigned
   server); the flow executor used the raw (null) `workspace_server_id`, so the agent CLI failed
   with "requires a workspace server". Fix: the executor resolves + sets `workspace_server_id`
   before running, mirroring the legacy phases.

## Validation result
After the fixes, run #47 completed end-to-end: CI → `pr_review` flow prompt (fp=2) → pipeline
fork → executor → server resolved (platform id 6) → `pr_fetch` fetched the diff (9806 chars) →
single `generate` agent call → finalization **posted the PR comment + flipped the label** →
`completed`. Full parity with the template path.

## Local agent execution — fixed
First pass: the posted review body was empty because claude (`needs_non_root=True`) was run by
the adapter as a non-root `coder` user that isn't provisioned in the local container (creds live
in `/root/.claude`). **Fix** (`backend/services/adapters/factory.py`): for a **local**
(in-container) server, run the agent as the container user (root) — or an explicitly-configured
non-root `worker_user` if set — never the remote `coder` default. After this, run **#48 produced
a real 3498-char review** and posted it to PR #31. Full end-to-end success with actual agent output.

## Bonus: the AI review caught a real bug (now fixed)
Claude's review of PR #31 flagged that Phase 3's default routed **any** `flow_prompt_id`-less run
to the implement flow — so a PR-review run whose `pr_review` prompt was absent/disabled would
wrongly run an implement (code-writing) job against a PR. **Fix** (`backend/worker/pipeline.py`):
`_defaults_to_implement_flow(run)` excludes `review_mode` runs from the implement default; they
fall through to the template path. Regression test added.

## Follow-up noted
- The flow executor uses the pure `run_agent_step`, which does **not** record an
  `AgentInvocation` — so flow runs currently lack per-run agent cost records. To wire up before
  Phase 5 (when templates/`phase_executions` are removed and flow becomes the only path).
- Devbox needs claude credentials before `FLOW_PROMPTS_ENABLED` is useful there.

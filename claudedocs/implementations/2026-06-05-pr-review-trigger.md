---
title: GitHub/Gitea PR-triggered AI code review
status: implemented
date: 2026-06-05
related:
  - claudedocs/plans/2026-06-05-pr-review-trigger.md
  - claudedocs/decisions/007-composable-step-workflows.md
---

# GitHub/Gitea PR-triggered AI code review

## What was built

PR review runs can now be launched two ways and post the AI review back as a PR comment:

1. **By label (webhook)** — a GitHub/Gitea `pull_request` event carrying the `ai-review`
   label routes through the restored `pr-review` workflow template.
2. **By CI (API)** — `POST /api/webhooks/pr-review` with `{repo, pr_number}` forces a review
   regardless of labels (explicit intent).

The review is single-pass: it fetches the PR diff via the provider API, runs one AI review,
and posts a summary comment. It never writes code or pushes to the PR branch.

## Key files

| File | Purpose |
|------|---------|
| `backend/services/webhook_security.py` | `verify_hmac_sha256()` — constant-time HMAC check (handles `sha256=` prefix) |
| `backend/api/_pr_webhook_helpers.py` | `read_verified_body`, `build_pr_review_run`, `handle_pr_event` shared by routes |
| `backend/api/webhooks_pr.py` | Routes: `github-pr`, `gitea-pr` (label-gated), `pr-review` (CI) |
| `backend/seed/workflow_templates.py` | Restored `pr-review` system template; removed from `_DEPRECATED_SYSTEM_TEMPLATES` |
| `backend/worker/phases/finalization.py` | Push to PR branch only when `review_mode == "fix"` |
| `backend/config.py` | `github_webhook_secret`, `gitea_webhook_secret` (optional HMAC) |

## How it works

1. **Trigger** → `webhooks_pr.handle_pr_event` reads the body (verifying HMAC when a secret is
   configured), ignores irrelevant actions, then asks `TriggerMatcher` for a template using a
   `pr_event` event with the PR's labels. The `pr-review` template's triggers carry
   `label_filter: ["ai-review"]`, so only labelled PRs match. No match → ignored, no run.
2. **Run creation** → `build_pr_review_run` binds the run to the `pr-review` template, sets
   `task_source_meta.review_mode = "comment"` and `run.max_retries = 0` (single pass).
3. **Pipeline** → `pr-review` template phases are `pr_fetch → reviewing → finalization`:
   - `pr_fetch` pulls the diff + comments by PR number into `coding_results` (API only, no checkout).
   - `reviewing` (`uses_agent=True`, `agent_mode="generate"`) reviews the pre-fetched diff.
     `max_retries=0` makes `should_retry()` return `False`, so the auto-fix loop never runs.
   - `finalization` posts `review_result` to the PR via `post_pr_comment()`; the
     `review_mode == "fix"` guard means a comment-mode run never pushes to the PR branch.

## Configuration

- **Label**: add `ai-review` to a PR (or its trigger) to request a review.
- **Webhook**: point the provider's `pull_request` webhook at `/api/webhooks/github-pr`
  (or `/api/webhooks/gitea-pr`).
- **HMAC (optional)**: set `GITHUB_WEBHOOK_SECRET` / `GITEA_WEBHOOK_SECRET`; unset = no verification.
- **CI**: `curl -X POST $HOST/api/webhooks/pr-review -H 'X-CI-Token: $TOKEN' -d '{"repo":"owner/name","pr_number":42}'`.
  When `CI_TRIGGER_SECRET` is set, `X-CI-Token` must match (constant-time) or the call is 401.
  When unset the endpoint is open (matches the other webhook routes) — set the secret and/or
  protect it at the network layer for production.

## Hardening (from adversarial review)

A multi-agent adversarial review surfaced and confirmed several issues, all fixed:

- **Autonomous-mode bypass (HIGH)** — `pipeline._resolve_workflow_phases` short-circuited on the
  project's `execution_mode` before honouring the run's template, so a PR-review run on an
  autonomous/hybrid/multi_agent project ran the coder/agent_loop against an un-checked-out
  workspace. Now a run carrying `review_mode` resolves the `pr-review` template first (by id, else
  by name) and **fails loudly** if it can't — never falling through to the coder pipeline.
- **Stale-trigger upgrade (HIGH)** — on DBs that still had an old `pr-review` system row with
  label-type triggers (never pruned), the seed left them untouched, so `TriggerMatcher` never
  matched the `pr_event` and the feature was silently dead. The seed now re-syncs
  `triggers`/`phases`/`description` for system templates that declare triggers (operator-owned
  `is_system=False` rows are still left alone).
- **CI auth (MEDIUM)** — optional `X-CI-Token` / `CI_TRIGGER_SECRET` (constant-time).
- **Robustness (LOW)** — non-ASCII signature header → 401 not 500; malformed JSON body → 400;
  `pr_number` must be `> 0`; in-flight dedupe (a second PR event while a review is pending/running
  is ignored); comment-mode finalization skips workspace/sandbox cleanup; `pr_fetch` now parses the
  changed-file list into the reviewer prompt; PR webhook gained the issue webhook's `project_id`
  fallback.

## Notes / limitations

- One summary comment per run (no inline/line-level comments).
- Diff-only review (generate mode) — the agent sees the diff, not a full checkout. A
  full-checkout, task-mode variant (richer context) is a future enhancement.
- GitLab/Bitbucket PR webhook routes are not added yet (their providers already implement
  `post_pr_comment`/`get_pr_diff`, so adding routes is mechanical).
- The CI endpoint supports an optional `X-CI-Token` shared secret (`CI_TRIGGER_SECRET`),
  enforced constant-time when set. It is fail-open when unset (consistent with the other
  webhook routes); set the secret and/or protect it at the network layer for production.

---
title: GitHub/Gitea PR-triggered AI code review
status: in-progress
date: 2026-06-05
related:
  - claudedocs/decisions/007-composable-step-workflows.md
  - claudedocs/decisions/006-multi-source-task-intake.md
---

# GitHub/Gitea PR-triggered AI code review

## Goal

When a pull request is opened/updated (gated by an `ai-review` label) **or** a CI job
calls our trigger endpoint, the platform launches a run that reviews the PR diff with an
AI agent and posts the review back as a PR comment.

## Background

All the building blocks already exist but were disconnected in the v0.5.x workflow
simplification:

- `pr_fetch` phase fetches the PR diff + comments by PR number (API only, no checkout).
- `reviewing` phase produces a structured `review_result` from the pre-fetched diff.
- `finalization` phase posts `review_result` to the PR via `post_pr_comment()`.
- `post_pr_comment()` / `get_pr_diff()` exist on all 4 git providers.
- `TriggerMatcher` already supports `pr_event` triggers with `label_filter`.

The gap: the `pr-review` workflow template that chained these was added to
`_DEPRECATED_SYSTEM_TEMPLATES` (deleted on boot), while `webhooks_pr.py` still looked it
up by name (`get_by_name("pr-review")` → always `None`). Result: PR webhooks created
runs with `workflow_template_id=None`, which fall back to the **implementation** default
template — the agent would try to *build* the PR body and open another PR instead of
reviewing.

## Scope

### In scope
- Restore the `pr-review` system template (`pr_fetch → reviewing → finalization`),
  generate-mode review, label-gated `pr_event` triggers for github + gitea.
- Rewrite `webhooks_pr.py` to route via `TriggerMatcher` (label-gated, like the issue
  webhooks) instead of the dead hardcoded lookup. Accept `opened`/`synchronize`/`labeled`/`reopened`.
- Force `max_retries=0` on review runs so the review is single-pass (no auto-fix of an
  un-checked-out workspace).
- Add a CI-friendly trigger endpoint `POST /api/webhooks/pr-review` (`repo` + `pr_number`).
- Optional HMAC signature verification (`github_webhook_secret`, `gitea_webhook_secret`).
- Guard `finalization._push_to_pr_branch` so review runs never push (gate on
  `review_mode == "fix"`).

### Out of scope
- Inline / line-level review comments (we post one summary comment).
- Full repo checkout + task-mode review (richer but heavier; future enhancement).
- GitLab/Bitbucket PR webhooks (providers support comments; webhook routes can follow).
- Frontend changes.
- Re-introducing the `fix-pr` template.

## Technical approach

1. **config.py** — add `github_webhook_secret: str = ""`, `gitea_webhook_secret: str = ""`.
2. **services/webhook_security.py** — `verify_hmac_sha256(secret, raw_body, signature_header)`
   (constant-time, tolerates `sha256=` prefix).
3. **seed/workflow_templates.py** — remove `"pr-review"` from `_DEPRECATED_SYSTEM_TEMPLATES`;
   add a `pr-review` entry to `DEFAULT_WORKFLOW_TEMPLATES`:
   - phases: `pr_fetch` → `reviewing(uses_agent=True, agent_mode="generate")` → `finalization`
   - triggers: `pr_event` for `github` and `gitea`, `label_filter: ["ai-review"]`
   - `is_default=False`, `is_system=True`
4. **api/webhooks_pr.py** — for each handler:
   - read raw body, verify HMAC when the secret is configured (401 on mismatch),
   - extract labels + action, build `pr_event` `TriggerEvent`, match a template,
   - if no template → `{status: ignored, reason: no_matching_template}` (no stray run),
   - create the run bound to the matched template, `task_source_meta.review_mode="comment"`,
     `run.max_retries = 0`.
   - Add `POST /api/webhooks/pr-review` (CI): look up project by `repo`, force the
     `pr-review` template by name, create a comment-mode review run.
5. **worker/phases/finalization.py** — only `_push_to_pr_branch` when
   `meta.get("review_mode") == "fix"`.

## Success criteria

- [x] `verify_hmac_sha256` unit-tested (valid, invalid, prefix, empty, non-ASCII).
- [x] Seed creates a `pr-review` template; not in deprecated set; double-seed stable; stale system rows reconciled.
- [x] PR webhook with `ai-review` label → run bound to `pr-review`, `review_mode="comment"`, `max_retries=0`.
- [x] PR webhook without `ai-review` label → ignored, no run.
- [x] PR webhook with a configured secret rejects a bad signature (401) and accepts a good one.
- [x] CI endpoint `POST /api/webhooks/pr-review` with `repo`+`pr_number` → review run created (optional `X-CI-Token`).
- [x] Finalization does not push for `review_mode="comment"`; still posts the review comment; skips workspace cleanup.
- [x] PR-review runs use their template even on autonomous-mode projects; fail loudly if unresolvable.
- [x] Existing seed/finalization/trigger tests stay green.
- [x] ruff + pyright clean on touched files; targeted tests pass in Docker.

## Review

Adversarial multi-agent review (4 dimensions × verify) ran on the diff: 14 confirmed findings,
3 dismissed (correctly). All HIGH/MEDIUM + the cheap LOW robustness items were fixed; the
deliberate fail-open-when-unset webhook posture and single-summary-comment scope are documented
limitations. See the implementation doc's "Hardening" section.

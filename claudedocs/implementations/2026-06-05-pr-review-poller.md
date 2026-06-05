---
title: PR-review polling (webhook-less) + label flip
status: implemented
date: 2026-06-05
related:
  - claudedocs/plans/2026-06-05-pr-review-poller.md
  - claudedocs/implementations/2026-06-05-pr-review-trigger.md
---

# PR-review polling (webhook-less) + label flip

## What was built

For a local server with no public webhook domain, the platform now **polls outbound** for
PRs that want an AI review — no inbound webhook needed (works against GitHub.com too).

- Add the `ai-review` label to a PR. Within ~1 minute the poller launches a review run.
- After the review, finalization flips the label to `ai-reviewed` (visible marker).
- By default a PR is reviewed **once**. To re-review after new commits, either re-add the
  `ai-review` label, or opt the project in to automatic re-review-on-push (below).
- Remove `ai-reviewed` to stop further reviews.

### Automatic re-review on new commits (opt-in)

Off by default. Set `integration_config.pr_review_rereview_on_push = true` on the project to
have the poller automatically re-review a PR when its head commit SHA changes. Without the
flag, a PR is reviewed once and not re-reviewed automatically.

## Key files

| File | Purpose |
|------|---------|
| `backend/services/task_source_polling/pr_review_poller.py` | `poll_pr_reviews()` — list PRs, filter `ai-review`/`ai-reviewed`, SHA-based dedup, create review run |
| `backend/worker/issue_poller_scheduler.py` | `_poll_project` also runs the PR poll for git projects (reuses cadence + `next_poll_at`) |
| `backend/services/git/{github,gitea,gitlab,bitbucket}.py` | `list_pull_requests`, `add_label`, `remove_label` |
| `backend/services/git/protocol.py` | the three new methods on the `GitProvider` Protocol |
| `backend/worker/phases/finalization.py` | `_flip_review_label` — `ai-review → ai-reviewed` (best-effort) |
| `backend/api/_pr_webhook_helpers.py` | `build_pr_review_run` stores `pr_head_sha` |

## How it works

1. The existing `IssuePollerScheduler` ticks every 60s and selects projects where
   `poll_enabled=True` and `next_poll_at` is due (per-project `poll_interval_minutes`, can be 1).
2. For each due project, `_poll_project` runs the normal issue poll **and** `poll_pr_reviews`.
3. `poll_pr_reviews` lists open PRs via `provider.list_pull_requests`, keeps those labelled
   `ai-review` or `ai-reviewed`, and for each decides via `_already_handled`:
   - **no prior review** for the PR → review (first review always proceeds);
   - a **pending/running** review for the PR → skip (never double-start);
   - a review already **attempted for this head SHA** (completed or failed) → skip (no retry storms);
   - a prior review exists for a **different commit** (a re-review) → skip **unless** the project
     set `integration_config.pr_review_rereview_on_push = true`;
   - otherwise → create a run bound to the `pr-review` template, `review_mode="comment"`,
     `max_retries=0`, with `pr_head_sha` stored in `task_source_meta`.
4. The run flows through `pr_fetch → reviewing → finalization`; finalization posts the comment
   and flips `ai-review → ai-reviewed` (best-effort — a label-API failure never fails the run).

**Dedup is DB-first**: the head SHA on the review `TaskRun` is the source of truth; the label
flip is a human-visible mirror. So even if the label flip fails, the SHA dedup still prevents
re-review of the same commit.

## Provider notes

- **GitHub**: `/pulls` for listing; labels via `issues/{n}/labels` (names work directly).
- **Gitea**: labels API needs numeric **ids**, so `add_label`/`remove_label` resolve the label
  name → id via `/labels` first; an unknown name is a safe no-op.
- **GitLab**: MRs via `/merge_requests`; labels via `add_labels`/`remove_labels` params.
- **Bitbucket**: lists PRs, but Cloud PRs have no labels — `add_label`/`remove_label` are no-ops,
  so Bitbucket PRs are not picked up by the poller (use the webhook/CI trigger instead).

## Enabling

- Set `poll_enabled=True` (and `poll_interval_minutes`, e.g. 1) on the project.
- Ensure the project's git token can read PRs and write labels.
- Create the `ai-review` and `ai-reviewed` labels in the repo (Gitea requires the label to
  exist before it can be applied).

## Hardening (from adversarial review)

A 3-dimension adversarial review (10 findings, 2 confirmed / 8 dismissed) flagged and fixed:

- **Token-resolution mismatch (MEDIUM)** — the poller originally resolved the git token only via
  the legacy `git_provider_token_enc` column, while finalization uses `get_project_token`
  (git_connections: project → server → global). For a project configured via `git_connections`
  the poll half would silently fall back to the global `.env` token — failing to list PRs, or
  authenticating as a different identity than the finalize half. The poller now resolves
  `git_connections` (project → global) first, then the legacy column.
- **Gitea label pagination (LOW)** — `_label_id` fetched only the first 100 labels; the flip
  now pages through them so a label past page 1 still resolves.

## Limitations

- One summary comment per review (no inline comments).
- A failed review for a given SHA is not auto-retried (avoids retry storms) — push a new commit
  or use the CI endpoint to force another pass.
- Bitbucket has no PR labels → not polled.

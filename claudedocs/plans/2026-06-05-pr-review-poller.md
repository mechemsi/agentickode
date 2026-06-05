---
title: PR-review polling (webhook-less) + label flip
status: in-progress
date: 2026-06-05
related:
  - claudedocs/plans/2026-06-05-pr-review-trigger.md
  - claudedocs/implementations/2026-05-02-notion-and-issue-polling.md
---

# PR-review polling (webhook-less) + label flip

## Goal

For a local server with no public webhook domain, poll git projects outbound every
~1 minute for open PRs labelled `ai-review` and launch a review run — re-reviewing when
the PR gets new commits, and flipping the label to `ai-reviewed` as a visible marker.

## Decisions (from the user)

- **Marking**: DB record is the source of truth for dedup (a review `TaskRun` for the PR's
  head SHA), **and** flip the label `ai-review → ai-reviewed` for human visibility.
- **Re-review**: yes, when new commits are pushed (head SHA changes).

## How it composes

`ai-review` = opt-in request. After a review, finalization flips it to `ai-reviewed` (the
visible "AI is managing this PR" marker). The poller treats PRs with **either** label as
candidates and uses the **head commit SHA** to decide whether a (re-)review is needed:

- no review run for this PR's current head SHA (and none in-flight) → create one;
- a run already exists for this SHA (pending/running/completed) → skip;
- head SHA changed since the last review → re-review.

To stop reviews on a PR, remove the `ai-reviewed` label.

## Scope

### In scope
- `GitProvider.list_pull_requests()` (GitHub, Gitea, GitLab, Bitbucket).
- `GitProvider.add_label()` / `remove_label()` (GitHub, Gitea, GitLab; Bitbucket = no-op).
- `pr_review_poller.poll_pr_reviews(project, session)` — SHA-based dedup, binds to the
  `pr-review` template, stores `pr_head_sha` in `task_source_meta`.
- Hook the poll into `IssuePollerScheduler._poll_project` (reuses cadence + `next_poll_at`,
  no new background service, no migration — gated on git provider + `poll_enabled`).
- Finalization flips the label for comment-mode reviews (best-effort).

### Out of scope
- New DB columns / migration (reuse `poll_enabled` + `poll_interval_minutes`).
- Bitbucket label flip (no label API) — review still runs, just no visible flip.
- Inline comments.

## Technical approach

1. **Providers** — add `list_pull_requests(repo_path, state="open", limit=50)` returning
   `{number, title, body, labels[str], head_ref, head_sha, html_url, state}`; and
   `add_label`/`remove_label(repo_path, number, label)`. Gitea resolves label name→id.
2. **`build_pr_review_run`** — accept `pr_head_sha` and store it in `task_source_meta`.
3. **`pr_review_poller`** — list PRs, keep those labelled `ai-review`/`ai-reviewed`, and for
   each create a review run unless a run for this PR + head SHA already exists
   (pending/running/completed). Reuses `decrypt_value` token + `get_git_provider`.
4. **Scheduler** — `_poll_project` also runs `poll_pr_reviews` for github/gitea/gitlab
   projects (guarded, errors swallowed).
5. **Finalization** — after posting the comment for a comment-mode run, flip
   `ai-review → ai-reviewed` (best-effort; failures logged, never fail the run).

## Success criteria

- [x] `list_pull_requests` parses number/labels/head_sha for GitHub + Gitea (+ GitLab/Bitbucket).
- [x] `add_label`/`remove_label` hit the right endpoints (Gitea resolves name→id).
- [x] Poller creates a review run for an `ai-review` PR; skips it on the next tick (same SHA);
      re-reviews after the head SHA changes; never double-starts an in-flight review.
- [x] Poller binds runs to the `pr-review` template with `review_mode="comment"`, `max_retries=0`,
      and `pr_head_sha` set.
- [x] Finalization flips the label for comment-mode runs; failures don't fail the run.
- [x] Scheduler runs the PR poll for git projects without breaking issue polling.
- [x] ruff + pyright clean; targeted tests pass in Docker.

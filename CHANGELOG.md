# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-05-24

The composable-workflow release. The fixed 8-phase pipeline is no longer the
only execution model — workflows are now composable arrays of `bash` and
`agent` steps with first-class triggers. The legacy pipeline is preserved as
the `default` workflow template. See [ADR-007](claudedocs/decisions/007-composable-step-workflows.md)
for the design rationale and [docs/workflows.md](docs/workflows.md) for the
full reference.

### Added

- Composable `bash` and `agent` step kinds with shared rules (`timeout_seconds`,
  `retry_count`, `failure_mode`, `trigger_mode`, `notify_source`).
- `{{run.X}}` and `{{steps.NAME.field}}` templating for inter-step data flow
  (`backend/worker/steps/templating.py`).
- First-class `WorkflowTemplate.triggers[]` field with five rule types:
  `label`, `issue_event`, `pr_event`, `schedule`, `manual`.
- `TriggerMatcher` service that routes every incoming event to matching
  templates (replaces ad-hoc per-source template lookup in webhook handlers).
- Webhook handlers (GitHub, Gitea, GitLab, Plane, Notion) now funnel through
  `TriggerMatcher`.
- `POST /api/workflow-templates/{id}/dry-run` — test whether a synthetic event
  would fire a template's triggers.
- Schedule trigger executor — scheduled-trigger poller that fires `schedule`
  workflows on cron ticks.
- Worktree-per-run workspace strategy — opt-in `workspace_strategy: worktree`
  with timestamped naming, pure path functions, idempotent create/remove
  (inspired by the myDash worktree pattern).
- Orphan worktree cleanup scheduler.
- UI step composer (`StepEditor`, `StepListEditor`, `GenericStepResult`).
- `GET /api/step-kinds` endpoint exposing per-kind `params_schema`.
- ADR-007 — Composable Step Workflows.
- `docs/workflows.md` — authoritative composable-workflow reference.

### Changed

- `WorkflowTemplates` page replaced by a step composer with kind selectors and
  per-kind param editors.
- `NewRun` per-step overrides are now pulled from the selected template instead
  of hardcoded against the 8-phase shape.
- `PhaseTimeline` no longer assumes the 8-phase shape — renders whatever step
  list the run actually executed.
- `RunDetail` renders bash/agent step results via kind-specific viewers instead
  of `phaseName === "coding"` branches.
- README and www marketing site rewritten around the composable model;
  www landing page tabs renamed from `Pipeline` to `Workflow` / `Composable Steps`.

### Deprecated

- Legacy phase modules (`planning`, `coding`, `testing`, `reviewing`,
  `approval`, `finalization`, `pr_fetch`, `task_creation`, `agent_loop`) are
  marked `kind: legacy_phase` in the phase registry. They remain discoverable
  and the `default` template uses them — no sunset date.
- Mirror of step results to `TaskRun.*_result` columns is removed for new
  writes; the read fallback stays until 0.6.0; columns dropped in 0.7.0.
- `docs/WORKER_PIPELINE.md` superseded by `docs/workflows.md`; redirect kept
  for link continuity.

### Migration

- Alembic migration 037 backfills existing `WorkflowTemplate.label_rules` into
  `triggers[type=label]`. No manual data migration needed — every template
  retains its previous label-routing behavior.
- ADR-005 (Multi-Agent Pipeline) is superseded by ADR-007.
- Per-phase prompt overrides stored under `RoleConfig.phase_binding` still
  work for `legacy_phase` steps. For new `agent` steps, put the prompt in
  `params.prompt` directly.

## [0.1.1] - 2026-03-12

### Changed
- Renamed project from AutoDev to AgenticKode
- Updated all branding, screenshots, and documentation

## [0.1.0] - 2026-03-11

### Added
- Initial open-source release
- 8-phase worker pipeline (workspace_setup, init, planning, coding, testing, reviewing, approval, finalization)
- Multi-provider git integration (GitHub, Gitea, GitLab, Bitbucket)
- Pluggable AI agents (Claude CLI, OpenAI Codex, GitHub Copilot, Google Gemini, Aider, Kimi, OpenCode, OpenHands)
- Remote workspace servers with SSH-based execution
- Workflow templates with label-based routing
- Per-project instructions and encrypted secrets
- Real-time UI with WebSocket log streaming and SSE dashboard updates
- SSH terminal bridge via xterm.js
- Notifications (Slack, Discord, Telegram, webhook)
- Webhook task sources (Plane, GitHub, Gitea, GitLab)
- Cost tracking with per-invocation token counting
- Backup/export with optional AES encryption
- GPU dashboard for Ollama server monitoring
- Comparison mode for parallel agent evaluation
- Role configs with per-agent prompt overrides

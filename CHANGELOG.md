# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.2] - 2026-05-24

Default workflow simplified to five composable steps, agent allowlist
narrowed to three CLIs, role machinery hidden from the UI ahead of
removal, and the marketing site brought back in sync.

### Added

- **Default workflow** — Single five-step recommended shape:
  `workspace_setup → init → implement (agent) → approval → finalization`.
  `workspace_strategy=worktree` is forced on the `workspace_setup` step
  so concurrent runs on the same project stay isolated. The `implement`
  prompt explicitly instructs the agent to commit, push, and create a
  PR/MR end-to-end. The `approval` step is a wait state where the
  operator can chat with the agent to give additional rules.
- **Two-template seed** — Only `default` and `example-composable` ship
  out of the box. Fresh installs see exactly these two; existing
  installs are migrated below.

### Changed

- **Agent allowlist** — UI surfaces only `claude`, `codex`, `opencode`.
  `aider`, `gemini`, `kimi`, `openhands` are filtered out of every
  agent picker (Chat, Settings, Agents page, per-server install
  panel). Backend `AgentSettings` rows are unchanged so existing
  chat sessions or runs pinned to those agents keep working; this is
  a UI-only hide.
- **Roles UI hidden** — Roles nav entry removed, role dropdowns
  dropped from the step editor (`AgentBody` + `LegacyPhaseBody`).
  Runtime resolver still works so existing templates execute
  unchanged. Full removal tracked in [#19](https://github.com/mechemsi/agentickode/issues/19).
- **www site** — Landing PipelineSection demo rewritten around the
  5-step default; FeaturesSection / StatsSection updated to the
  three-agent allowlist; docs sections on Role Configs removed;
  workspace-servers.md gained a "Per-project and per-step overrides"
  section documenting v0.5.1 `local_path` / `worker_user_override` /
  `run_as` / `workspace.default_root`.

### Migration

- The default `default` workflow template is auto-upgraded in place
  from the legacy 8-phase shape to the new 5-step shape **only** when
  the row hasn't been edited by the operator (phase name sequence
  matches the historical default exactly). Operator-edited rows are
  left alone.
- The five legacy label-routed system templates (`planner`, `hotfix`,
  `small-task`, `pr-review`, `fix-pr`) are deleted from existing DBs on
  backend boot. Only `is_system=true` rows are touched; operator
  templates that happen to share a name are left alone. Historic
  `task_runs` rows referencing these templates have their
  `workflow_template_id` NULLed before delete so the FK cascade
  doesn't fail (column is nullable; run history is preserved).
- No new schema migration required — all changes are seed-level.

## [0.5.1] - 2026-05-24

Workspace configuration patch — makes AutoDev usable from a developer host
(e.g. WSL) without running as `root` and without re-cloning a repo that's
already checked out locally. All three knobs are opt-in and the previous
default behavior is unchanged.

### Added

- `ProjectConfig.local_path` — when set, `workspace_setup` validates the
  path (exists, is a git repo, working tree clean) and uses it directly,
  skipping clone/fetch/scaffold. Dirty tree → `LocalPathError` before any
  side-effect. Worktree strategy is auto-forced under
  `<local_path>/.worktrees/` so concurrent runs stay isolated.
- `ProjectConfig.worker_user_override` and `step.params.run_as` —
  per-project and per-step worker-user overrides. `bash_step` wraps the
  rendered command in `runuser -l`; `agent_step` temporarily flips
  `CLIAdapter.worker_user` and restores it in a `finally` so concurrent
  runs sharing the adapter aren't affected.
- `workspace.default_root` `AppSetting` — new workspace servers inherit
  this value when no `workspace_root` is supplied in the create body.
  Surfaced in the Settings page as a new "Workspace" section.
- `validate_username(name)` boundary check enforcing
  `[a-z_][a-z0-9_-]{0,31}$?`. Applied at every entry that flows into
  `runuser`/`chown` (server.worker_user, project override, step
  `run_as`). Unsafe values surface as a clear `UsernameError`
  pre-flight rather than a confusing shell error mid-run.
- Two new dependency-security fixes (PR #16, issue #9): backend
  `pytest` 8.3.4 → 9.0.3 (CVE-2025-71176) plus `pytest-asyncio` →
  1.3.0; frontend `npm audit fix` resolved 7 transitive advisories
  (`@xmldom/xmldom`, `brace-expansion`, `dompurify`, `flatted`,
  `picomatch`, `postcss`, `vite`, `ws`).

### Changed

- `workspace_setup` chown / `safe.directory` wrapping now fires when
  the executor is the local platform server too (not only when SSH
  user is `root`), and is a no-op when the executor already runs as
  the target user.
- All `chown` interpolations of `worker_user` are now `shlex.quote`'d
  (workspace root, worktree dir, `CLIAdapter._check_status`) as
  defense-in-depth alongside the new validator.

### Fixed

- Three Copilot review findings on PR #17 resolved before merge:
  `needs_user_drop` no-op guard for non-root local executors,
  unquoted `chown` interpolation, and `run_as` flowing into
  `CLIAdapter.worker_user` without validation.

### Migration

- Alembic migration `038_workspace_config` adds
  `project_configs.local_path` and `project_configs.worker_user_override`
  (both `Text NULL`). Backfill is a no-op — every existing project
  keeps today's behavior (clone every run, use server default user).
- `workspace.default_root` lives in the existing `app_settings` KV
  table; no new schema for it.

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

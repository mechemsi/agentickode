# Project Documentation Index

Quick reference for all project documentation. Claude reads this first to find relevant context.

## Plans

| Doc | Status | Date | Summary |
|-----|--------|------|---------|
| [PR-triggered AI code review](plans/2026-06-05-pr-review-trigger.md) | implemented | 2026-06-05 | `ai-review` label / CI endpoint launches a PR review run that comments on the PR |
| [PR-review polling (webhook-less)](plans/2026-06-05-pr-review-poller.md) | implemented | 2026-06-05 | Outbound poller for `ai-review` PRs (no webhook domain); SHA-based re-review + label flip |
| [Remove the roles abstraction](plans/2026-06-05-remove-roles.md) | implemented | 2026-06-05 | Workflow steps name the agent directly; delete RoleResolver/RoleAssignment/RoleConfig |
| [Simplify project creation](plans/2026-06-08-simplify-project-creation.md) | implemented | 2026-06-08 | Minimal create form: git URL + slug only; all other fields hidden behind "Advanced" toggle |
| [Docs & site agentic update](plans/2026-06-08-docs-agentic-update.md) | implemented | 2026-06-08 | Reframed README, CLAUDE.md, skills, legacy docs (autodev#39) AND the agentickodeweb marketing site (agentickodeweb#3) to the flow-prompt/ADR-009 agentic model; RoleResolver→AgentResolver |
| [Replace workflow templates with flow prompts](plans/2026-06-08-workflows-to-flow-prompts.md) | planned | 2026-06-08 | Drop `WorkflowTemplate` + phase-step dispatch; replace with single flow-prompt + agent. Pre-design doc; ADR-009 required before implementation. |
| [Multiple workspace folders on platform server](plans/2026-06-08-multi-workspace-folders.md) | implemented | 2026-06-08 | Add `workspace_folders` JSONB to WorkspaceServer; multi-root scan/discovery; platform server UI |
| [Terminal + Chat Agent Launch as Selected User](plans/2026-06-08-launch-as-user.md) | implemented | 2026-06-08 | Terminal PTY + chat agent + tmux sessions + LaunchAgentModal all run as `worker_user` via `runuser` (no-op when unset); migration 042 |
| [Host machine as default platform workspace](plans/2026-06-08-host-default-workspace.md) | partial | 2026-06-08 | `gh` check + run-as-user seeding + SSH-to-host switch (all OFF by default via `PLATFORM_*`); host-side sshd setup is operator's step |
| *Plans are in `docs/plans/` — migrate here as they are updated* | | | |

## Implementations

| Doc | Date | Summary |
|-----|------|---------|
| [Research: Autonomous Platform](../claudedocs/research_autonomous_platform_integrations_20260328.md) | 2026-03-28 | Research notes on autonomous agent scheduling and self-sustaining loops |
| [Notion + issue polling](implementations/2026-05-02-notion-and-issue-polling.md) | 2026-05-02 | Notion task source (webhook + poller + bidirectional manager) and generic issue-polling fallback for all trackers |
| [PR-triggered AI code review](implementations/2026-06-05-pr-review-trigger.md) | 2026-06-05 | Restored `pr-review` template; label-gated PR webhooks + CI endpoint + HMAC; comment-mode finalization guard |
| [PR-review polling (webhook-less)](implementations/2026-06-05-pr-review-poller.md) | 2026-06-05 | Outbound poller + provider `list_pull_requests`/`add_label`/`remove_label`; SHA dedup; `ai-review→ai-reviewed` flip |
| [Remove the roles abstraction](implementations/2026-06-05-remove-roles.md) | 2026-06-05 | `AgentResolver` + per-step `agent` field + project/global default; deleted role models/APIs/UI; migration 039/040 |
| [Simplify project creation](implementations/2026-06-08-simplify-project-creation.md) | 2026-06-08 | Minimal `ProjectForm` (URL + name + polling) with Advanced disclosure for autopopulated fields |
| [gh CLI check + multiple workspace folders](implementations/2026-06-08-gh-check-and-workspace-folders.md) | 2026-06-08 | `check_gh_cli` endpoint + GitAccessPanel badge; `workspace_folders` JSONB multi-root scan + form UI (migration 041) |
| [Platform run-as-user + SSH-to-host scaffolding](implementations/2026-06-09-host-execution-runuser.md) | 2026-06-09 | Terminal/chat run as `worker_user` via `runuser`; `PLATFORM_*` config + seed switch to SSH-to-host (OFF by default); runbook |
| [Flow prompts — Phase 1](implementations/2026-06-09-flow-prompts-phase1.md) | 2026-06-09 | ADR-009 Phase 1 (additive, flag-gated): `flow_prompts` table + `flow_prompt_id` + data-source registry + single-agent-call executor; off by default (migration 043) |
| [Flow prompts — Phase 2 (PR-review)](implementations/2026-06-09-flow-prompts-phase2-pr-review.md) | 2026-06-09 | ADR-009 Phase 2: poller/webhook bind PR-review to the `pr-review` flow prompt (flag-gated); executor sets `review_result` → finalization posts comment + flips label (parity) |
| [Flow prompts — Phase 3 (default)](implementations/2026-06-09-flow-prompts-phase3-default.md) | 2026-06-09 | ADR-009 Phase 3: flag on → runs default to the `implement` flow prompt; template creation deprecated (warning) |
| [Flow prompts — live validation + fixes](implementations/2026-06-09-flow-prompts-validation.md) | 2026-06-09 | Live PR-review run validated the flow engine; fixed CI-endpoint flow binding + executor server resolution; local non-root agent-user caveat |

## Decisions

| Doc | Date | Summary |
|-----|------|---------|
| [001 — Local LLMs First](decisions/001-local-llm-first.md) | 2026-02 | Local LLMs (Ollama) as the default backend, not cloud APIs |
| [003 — Workspace Types](decisions/003-workspace-types.md) | 2026-02 | Three workspace types: local, SSH remote, container |
| [005 — Multi-Agent Pipeline](decisions/005-multi-agent-pipeline.md) | 2026-02 | Superseded by ADR-007 — see below |
| [006 — Multi-Source Task Intake](decisions/006-multi-source-task-intake.md) | 2026-03 | Webhooks from Plane, GitHub, Gitea, GitLab for task ingestion |
| [007 — Composable Step Workflows](decisions/007-composable-step-workflows.md) | 2026-05 | Generic bash + agent step kinds; legacy phases preserved as kind: legacy_phase; triggers as first-class |
| [008 — Direct Agent Selection](decisions/008-direct-agent-selection.md) | 2026-06 | Remove roles; workflow steps name the agent; project/global default; irreversible table drop |
| [009 — Flow Prompts](decisions/009-flow-prompts.md) | 2026-06 | Replace workflow templates with a single agent call (prompt + fetched data); supersedes ADR-007; drop phase_executions + workflow_templates; deprecate comparison; 5-phase rollout |

## Reference Docs

| Doc | Summary |
|-----|---------|
| [Workflows reference (`docs/workflows.md`)](../docs/workflows.md) | Composable step kinds, triggers, templating, workspace strategies, migration from the legacy pipeline. Authoritative ref for ADR-007. |
| [Worker pipeline (`docs/WORKER_PIPELINE.md`)](../docs/WORKER_PIPELINE.md) | Legacy 8-phase pipeline reference (deprecated; preserved as the `default` template — see `workflows.md`). |

## Runbooks

| Doc | Summary |
|-----|---------|
| [Database Migration](runbooks/database-migration.md) | How to create, test, and deploy Alembic migrations in Docker |
| [Release Checklist](runbooks/release-checklist.md) | Steps for tagging, building, and shipping a release |
| [Platform host execution](runbooks/platform-host-execution.md) | Enable `PLATFORM_USER` (run-as) and `PLATFORM_SSH_HOST` (SSH-to-host) for the platform server |

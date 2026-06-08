# Project Documentation Index

Quick reference for all project documentation. Claude reads this first to find relevant context.

## Plans

| Doc | Status | Date | Summary |
|-----|--------|------|---------|
| [PR-triggered AI code review](plans/2026-06-05-pr-review-trigger.md) | implemented | 2026-06-05 | `ai-review` label / CI endpoint launches a PR review run that comments on the PR |
| [PR-review polling (webhook-less)](plans/2026-06-05-pr-review-poller.md) | implemented | 2026-06-05 | Outbound poller for `ai-review` PRs (no webhook domain); SHA-based re-review + label flip |
| [Remove the roles abstraction](plans/2026-06-05-remove-roles.md) | implemented | 2026-06-05 | Workflow steps name the agent directly; delete RoleResolver/RoleAssignment/RoleConfig |
| [Simplify project creation](plans/2026-06-08-simplify-project-creation.md) | planned | 2026-06-08 | Minimal create form: git URL + slug only; all other fields hidden behind "Advanced" toggle |
| [Docs & site agentic update](plans/2026-06-08-docs-agentic-update.md) | planned | 2026-06-08 | Update README, CLAUDE.md, skills, and agentickodeweb site to reflect agentic model; remove stale roles/8-phase framing |
| [Replace workflow templates with flow prompts](plans/2026-06-08-workflows-to-flow-prompts.md) | planned | 2026-06-08 | Drop `WorkflowTemplate` + phase-step dispatch; replace with single flow-prompt + agent. Pre-design doc; ADR-009 required before implementation. |
| [Multiple workspace folders on platform server](plans/2026-06-08-multi-workspace-folders.md) | planned | 2026-06-08 | Add `workspace_folders` JSONB to WorkspaceServer; multi-root scan/discovery; platform server UI |
| [Terminal + Chat Agent Launch as Selected User](plans/2026-06-08-launch-as-user.md) | planned | 2026-06-08 | Terminal bridge and chat-launched agents run as `WorkspaceServer.worker_user` on the platform server |
| [Host machine as default platform workspace](plans/2026-06-08-host-default-workspace.md) | planned | 2026-06-08 | Make the platform server represent the real host; pin to a run-as user; add `gh` CLI health check |
| *Plans are in `docs/plans/` — migrate here as they are updated* | | | |

## Implementations

| Doc | Date | Summary |
|-----|------|---------|
| [Research: Autonomous Platform](../claudedocs/research_autonomous_platform_integrations_20260328.md) | 2026-03-28 | Research notes on autonomous agent scheduling and self-sustaining loops |
| [Notion + issue polling](implementations/2026-05-02-notion-and-issue-polling.md) | 2026-05-02 | Notion task source (webhook + poller + bidirectional manager) and generic issue-polling fallback for all trackers |
| [PR-triggered AI code review](implementations/2026-06-05-pr-review-trigger.md) | 2026-06-05 | Restored `pr-review` template; label-gated PR webhooks + CI endpoint + HMAC; comment-mode finalization guard |
| [PR-review polling (webhook-less)](implementations/2026-06-05-pr-review-poller.md) | 2026-06-05 | Outbound poller + provider `list_pull_requests`/`add_label`/`remove_label`; SHA dedup; `ai-review→ai-reviewed` flip |
| [Remove the roles abstraction](implementations/2026-06-05-remove-roles.md) | 2026-06-05 | `AgentResolver` + per-step `agent` field + project/global default; deleted role models/APIs/UI; migration 039/040 |

## Decisions

| Doc | Date | Summary |
|-----|------|---------|
| [001 — Local LLMs First](decisions/001-local-llm-first.md) | 2026-02 | Local LLMs (Ollama) as the default backend, not cloud APIs |
| [003 — Workspace Types](decisions/003-workspace-types.md) | 2026-02 | Three workspace types: local, SSH remote, container |
| [005 — Multi-Agent Pipeline](decisions/005-multi-agent-pipeline.md) | 2026-02 | Superseded by ADR-007 — see below |
| [006 — Multi-Source Task Intake](decisions/006-multi-source-task-intake.md) | 2026-03 | Webhooks from Plane, GitHub, Gitea, GitLab for task ingestion |
| [007 — Composable Step Workflows](decisions/007-composable-step-workflows.md) | 2026-05 | Generic bash + agent step kinds; legacy phases preserved as kind: legacy_phase; triggers as first-class |
| [008 — Direct Agent Selection](decisions/008-direct-agent-selection.md) | 2026-06 | Remove roles; workflow steps name the agent; project/global default; irreversible table drop |

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

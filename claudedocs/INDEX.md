# Project Documentation Index

Quick reference for all project documentation. Claude reads this first to find relevant context.

## Plans

| Doc | Status | Date | Summary |
|-----|--------|------|---------|
| *Plans are in `docs/plans/` — migrate here as they are updated* | | | |

## Implementations

| Doc | Date | Summary |
|-----|------|---------|
| [Research: Autonomous Platform](../claudedocs/research_autonomous_platform_integrations_20260328.md) | 2026-03-28 | Research notes on autonomous agent scheduling and self-sustaining loops |
| [Notion + issue polling](implementations/2026-05-02-notion-and-issue-polling.md) | 2026-05-02 | Notion task source (webhook + poller + bidirectional manager) and generic issue-polling fallback for all trackers |

## Decisions

| Doc | Date | Summary |
|-----|------|---------|
| [001 — Local LLMs First](decisions/001-local-llm-first.md) | 2026-02 | Local LLMs (Ollama) as the default backend, not cloud APIs |
| [003 — Workspace Types](decisions/003-workspace-types.md) | 2026-02 | Three workspace types: local, SSH remote, container |
| [005 — Multi-Agent Pipeline](decisions/005-multi-agent-pipeline.md) | 2026-02 | Superseded by ADR-007 — see below |
| [006 — Multi-Source Task Intake](decisions/006-multi-source-task-intake.md) | 2026-03 | Webhooks from Plane, GitHub, Gitea, GitLab for task ingestion |
| [007 — Composable Step Workflows](decisions/007-composable-step-workflows.md) | 2026-05 | Generic bash + agent step kinds; legacy phases preserved as kind: legacy_phase; triggers as first-class |

## Runbooks

| Doc | Summary |
|-----|---------|
| [Database Migration](runbooks/database-migration.md) | How to create, test, and deploy Alembic migrations in Docker |
| [Release Checklist](runbooks/release-checklist.md) | Steps for tagging, building, and shipping a release |

---
title: Replace workflow templates with flow prompts (single agent call)
status: accepted
date: 2026-06-09
related:
  - claudedocs/decisions/005-multi-agent-pipeline.md
  - claudedocs/decisions/007-composable-step-workflows.md
  - claudedocs/decisions/008-direct-agent-selection.md
  - claudedocs/plans/2026-06-08-workflows-to-flow-prompts.md
---

# 009 — Flow prompts (single agent call)

## Context

A run is currently driven by a **`WorkflowTemplate`**: an ordered list of phases/steps
(composable bash + agent steps, ADR-007) dispatched by `pipeline.py`, with per-step results
recorded in `phase_executions` and cost in `agent_invocations.phase_execution_id`. Label/PR
routing picks a template via `TriggerMatcher`; comparison mode forks the `coding` phase into
two agents; PR-review is a template whose `reviewing` phase runs `generate` on a fetched diff.

After ADR-008 removed the roles layer, the next abstraction down — the static workflow/phase
engine — is itself largely unused ceremony for a single-local-server deployment running modern
agentic CLIs. The product direction (Notion task "Replace server workflows with flow prompts"):
**give an agent a prompt + the data we fetch, and let it run** (the agent decides the steps),
similar to a Paperclip-style autonomous run.

## Options considered

1. **Keep workflow templates** — no change. Con: maintains a multi-step dispatch engine,
   `phase_executions`, template CRUD/UI, and trigger matching that the agentic model makes redundant.
2. **Rename only** (`WorkflowTemplate` → `FlowPrompt`, keep step composition) — low risk (~2d) but
   keeps the multi-step machinery; doesn't deliver the simplification.
3. **Full simplification: a flow prompt is a single agent call** — chosen.

## Decision

A **flow prompt** is a single agent invocation: a named prompt + a set of platform-fetched
data inputs. The pipeline runs builtin `workspace_setup` → `init`, **fetches the flow's data**,
renders the prompt, calls the agent **once** (`run_task`, or `generate` for diff-only flows),
optionally gates on approval, then `finalization`. The agent's return is the run outcome; there
are no dynamic per-step `phase_executions`.

Resolved open questions (Dominykas, Notion, 2026-06-09):

| # | Question | Decision |
|---|----------|----------|
| OQ-1 | Audit/`phase_executions` fate | **Drop** `phase_executions`; the single result lands in `task_runs.coding_results`. `agent_invocations` keeps run-level cost (drop its `phase_execution_id` FK). Historical per-step detail is lost (accepted). |
| OQ-2 | What data is auto-fetched | **Fixed per flow type** (e.g. `pr_review` always fetches the PR diff + comments; `implement` fetches repo/issue context) **and additionally declarable per prompt**. |
| OQ-5 | Comparison (A/B) mode | **Deprecate** — remove comparison mode and its `coding`-phase fork. |
| OQ-7 | `task_runs.workflow_template_id` migration | **Drop** the `workflow_templates` table; null the FK on existing runs (historical template linkage lost, irreversible — accepted). |

Supersedes **ADR-007** (composable bash+agent steps) and reframes **ADR-005** (multi-agent
pipeline): multi-step composition and comparison are removed. Custom multi-step templates break
with no migration path (accepted). PR-review becomes a flow prompt (different prompt + `generate`
mode), not a special template.

## Rationale

The flexibility of templates/steps/roles was built for a multi-server fleet that never
materialised. Agentic CLIs already plan-and-execute internally, so a single prompt + fetched
context is sufficient and far simpler to operate, reason about, and cost-track. The user accepts
the loss of historical step/template audit detail in exchange for removing the engine.

## Consequences

- **Removed:** `WorkflowTemplate` model/CRUD/UI/seed, `TriggerMatcher` template selection,
  `phase_executions` table + repo, composable step kinds, comparison mode (`_comparison.py`),
  dynamic phase dispatch in `pipeline.py`.
- **Added:** a `flow_prompts` table (prompt text + data-source declarations + triggers), a
  per-flow-type fixed data-fetch layer, and a slimmed pipeline (setup → fetch → single agent →
  approval? → finalize).
- **Irreversible migration:** dropping `workflow_templates`/`phase_executions` loses historical
  linkage and per-step records. Ship behind a feature flag and stage the drops last.
- **PR-review / webhooks / poller** must be re-pointed at the `pr_review` flow prompt before the
  template path is removed (must not break the live PR-review feature).
- Approval gates and session-resume are preserved (they hang off the run, not the steps).

## Phasing (gate each before the next)

1. Add `flow_prompts` table + per-flow-type data fetch + feature flag (additive, no removals).
2. Port PR-review to a flow prompt; re-point poller/webhooks; verify parity.
3. Default new runs to flow prompts; deprecate template creation in the UI.
4. Remove `WorkflowTemplates` UI + comparison mode.
5. Remove `WorkflowTemplate` API/model + `phase_executions`; drop tables (irreversible).

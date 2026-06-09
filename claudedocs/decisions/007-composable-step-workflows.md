# ADR-007: Composable Step Workflows

## Status

Superseded by [ADR-009](009-flow-prompts.md) (2026-06-09) — flow prompts replace composable
multi-step workflows with a single agent call. Accepted (2026-05-23).

## Context

[ADR-005](005-multi-agent-pipeline.md) ratified an 8-phase pipeline — `workspace_setup → init → planning → coding → testing → reviewing → approval → finalization` — where each phase was a distinct domain module with a specialized role (planner / coder / reviewer) and, originally, a different model size (32B / 24B / 14B).

Two things have changed since that decision was written.

**1. The "specialized agent per phase" premise no longer reflects how agents actually work.** Modern coding agents — Claude Code, Codex, OpenHands, Gemini CLI — routinely do plan + code + test + review inside a single session. The per-phase decomposition we ship today is a framework abstraction layered *on top of* an agent that already does all four steps internally. The result is LARP-style specialization: we invoke the same agent three or four times in a row, paying the session-startup cost each time, while the agent re-derives context that another instance of the same agent just produced. The original "independent reviewer catches errors" argument from ADR-005 still has some force when the planner and reviewer are genuinely different models, but no team running the default Claude template gets that benefit, and the framework gives them no way to opt out.

**2. The flexibility we need is already in the storage layer — it's just hidden from users.** Per the current-state snapshot at [`research/2026-05-23-current-pipeline-state.md`](../research/2026-05-23-current-pipeline-state.md):

- `WorkflowTemplate.phases` is a `JSONB` array of free-form `PhaseConfig` rows (snapshot §3). Nothing in the DB schema enforces the 8 names.
- `PhaseConfig.params`, `cli_flags`, `environment_vars`, `command_templates` are all open `dict`s (snapshot §2). The pipeline accepts and persists extra keys (e.g. `delay_seconds`) that aren't in the Pydantic schema at all.
- `discover_phases()` walks the `backend/worker/phases/` directory at runtime — phase modules are already a plugin registry (snapshot §1, lines 38).
- `CommandExecutor` (`backend/services/workspace/command_executor.py`) is a generic bash primitive that every workspace-touching phase already routes through.
- `CLIAdapter.generate(...)` plus `RoleResolver` already abstract "run an agent against a prompt, capture the response."

What's missing isn't infrastructure — it's a primitive for composing these pieces without writing a new phase module, and a frontend / docs story that treats step composition as the headline UX instead of a hidden capability.

**3. The fixed 8-phase shape blocks valid non-coding use cases.** A workflow that "fetches a Sentry alert, runs an agent to summarize it, posts to Slack" doesn't need `planning` or `reviewing` or `approval`; it just needs `agent` + `bash`. Today users either bend a coding template into doing this (skipping 5 of 8 phases and using `phase_overrides` to redirect the remaining 3) or fork the codebase. Neither is acceptable.

**4. The implicit inter-phase data flow is fragile.** Per snapshot §5, the contract that `coding` reads `planning_result.subtasks` and `reviewing` reads `coding_results.session_id` is encoded as direct attribute reads on `TaskRun`, mirrored from `PhaseExecution.result` via the hardcoded `_LEGACY_RESULT_MAP` (snapshot §5, lines 206–216). Adding a step between `planning` and `coding` requires editing both modules. Removing a step risks downstream `KeyError`s. Users can't introspect what data a step produces or consumes.

## Options Considered

### Option A — Keep 8 phases, improve configuration UI

Treat the 8-phase shape as canonical. Invest in making per-phase customization (custom prompts, custom commands, per-phase agent override) more discoverable and easier to edit in the frontend. Don't add new step primitives.

**Pros**
- Zero backend churn — the most conservative path.
- The 8-phase narrative is already documented (README, WORKER_PIPELINE.md, www site, several blog posts) and users have built mental models around it.
- No migration burden for existing templates or external integrations reading legacy `TaskRun.*_result` columns.

**Cons**
- Doesn't fix the core mismatch with how single-session agents work — users still pay the per-phase startup cost.
- Doesn't unblock non-coding workflows (monitoring response, docs updates, scheduled checks).
- Doesn't expose the flexibility the storage layer already supports — the framework keeps lying about its own capabilities.
- The implicit data-flow contracts (`planning_result.subtasks → coding`) stay implicit, so adding even one step requires a code change.

### Option B — Composable `bash` and `agent` step kinds, legacy phases preserved as `kind: legacy_phase`

Introduce two generic step primitives — `bash` (run a shell command on the workspace) and `agent` (invoke a role through `CLIAdapter`) — that are composable in any workflow template alongside the existing phase modules. Every existing phase module (`planning.py`, `coding.py`, etc.) is tagged `kind: legacy_phase` and remains discoverable indefinitely. `workspace_setup` and `init` stay as an immutable prelude (`kind: builtin`) — they always run, before any user-composed step. Inter-step data flow becomes explicit via `{{steps.NAME.field}}` templating against `PhaseExecution.result`. Triggers (which workflow runs when X happens) become a first-class `WorkflowTemplate.triggers[]` field instead of being scattered across webhook handlers.

**Pros**
- Additive — no breaking change. Every existing template (the 6 seeded ones + any user-authored ones) continues to run.
- Matches what agents actually do today: one agent, one session, one composed step that does the work end-to-end. Multi-agent pipelines remain possible via composition.
- Builds on infrastructure that already exists (`CommandExecutor`, `CLIAdapter`, `WorkflowTemplate.phases` JSONB, auto-discovery registry). No new storage layer, no new agent abstraction.
- Unlocks valid non-coding workflows (monitoring, docs, scheduled jobs) without forking the codebase.
- Makes data flow explicit and inspectable — users see "step `plan` outputs `subtasks`, step `code` references `{{steps.plan.subtasks}}`."
- Frontend rewrite is needed regardless (see Phase 3 of the overhaul plan) — this option gives the rewrite something meaningful to expose.

**Cons**
- Frontend rewrite is non-trivial (~12 tasks, one full PR — Phase 3 of the plan).
- Docs debt: README, `docs/WORKER_PIPELINE.md`, the www marketing site, and several blog posts all lead with the "8-phase pipeline" narrative and need to be rewritten (~9 tasks — Phase 6 of the plan).
- Existing per-phase prompt overrides (`RoleConfig.phase_binding`) need to be reframed as per-step prompts; we need a migration / shim for users who have customized them.
- Templating engine is new surface area (even hand-rolled at ~50 lines). Has to be safe against untrusted input from `task.title` / `task.description`.

### Option C — Hard rewrite: rip out per-domain phases, force everything through generic step kinds

Delete `planning.py`, `coding.py`, `testing.py`, `reviewing.py`, etc. Every workflow expresses its logic as a graph of `bash` and `agent` steps. The 6 seeded templates get rewritten by hand. External integrations reading `TaskRun.planning_result` etc. break.

**Pros**
- Cleanest end state — one mental model, no legacy ambiguity.
- Smaller codebase — ~9 phase modules deleted.
- No "two ways to do the same thing" confusion.

**Cons**
- Breaks every existing user-authored workflow template the day we ship.
- Breaks any external system reading `TaskRun.coding_results.pr_diff` or similar (snapshot §5, lines 222–231 lists the full contract surface).
- Loses the genuine value some legacy phases encapsulate (`workspace_setup`'s clone-and-checkout sequence; `approval`'s human-gate-then-park-the-run mechanic; `finalization`'s PR merge + cleanup) — these would have to be re-implemented as either new `kind: builtin` steps or as fixed bash scripts users copy-paste into every template.
- Risk: at least one of the 9 phase modules will encode some subtle behavior we don't notice until production breaks.
- Forces a big-bang migration on a feature that should be rolled out incrementally.

## Decision

**Option B.**

The framework will offer two generic step kinds — `bash` and `agent` — composable in any workflow template. All existing phase modules continue to work, tagged as `kind: legacy_phase`. `workspace_setup` and `init` are reclassified as `kind: builtin` and remain an immutable prelude that runs before any user-composed step. Triggers move to a first-class `WorkflowTemplate.triggers[]` field. Inter-step data flow is explicit via `{{steps.NAME.field}}` templating.

## Rationale

Option B wins on five concrete grounds, in priority order:

1. **It's additive, not destructive.** Every existing template (default, planner, hotfix, small-task, pr-review, fix-pr) keeps running on every commit to main. External integrations reading legacy `TaskRun.*_result` columns keep working for at least one release cycle. The overhaul ships as 7 reviewable PRs (Phase 0 through Phase 6 of the [overhaul plan](../plans/2026-05-23-agentic-workflow-overhaul.md)) instead of one unreviewable mega-merge. Option C cannot offer this and Option A doesn't earn the breakage budget Option C would spend.

2. **It matches what real agents do.** A single `kind: agent` step invoking a Claude Code or Codex session can plan, code, test, and self-review in one pass — which is what the agent does anyway. The per-phase decomposition stays available for users who genuinely want a multi-agent pipeline with different models (the original ADR-005 use case), but it's no longer the only shape on offer. Option A keeps the LARP; Option B retires it without forcing it on anyone.

3. **The storage layer is already there.** `WorkflowTemplate.phases` is JSONB, `PhaseConfig.params` is an open dict, `PhaseExecution.phase_config` round-trips arbitrary keys, the phase registry is auto-discovered. We're exposing existing capability, not building new infrastructure. The actual new code is `BashStepRunner`, `AgentStepRunner`, a 50-line templating helper, and one migration to add `WorkflowTemplate.triggers`. Option A would leave this latent capability hidden; Option C would tear it out and rebuild.

4. **Frontend rewrite is needed regardless.** Per the current-state snapshot §1, the frontend has hardcoded phase-name lists in `PhaseTimeline.tsx`, `NewRun.tsx`, `RunDetail.tsx`, and `WorkflowTemplates.tsx` — including a known pre-existing inconsistency (`PHASES_WITH_AGENTS` is missing `testing` and `approval`). Any improvement to the workflow UX has to fix this. Option B gives the rewrite a coherent target (step kinds, generic step-result viewer, trigger editor); Option A leaves the rewrite hunting for justification.

5. **It unblocks non-coding use cases.** Monitoring-alert response, docs updates, scheduled audits, cron-driven outbound messages — all of these are workflows the framework should support and today blocks behind a fixed coding shape. Option A explicitly punts on this; Option C technically enables it but at the cost of breaking everything else. Option B gives us both.

## Consequences

### Wins

- **Per-step prompt customization is now first-class.** `RoleConfig.phase_binding` (per-phase prompt overrides) becomes per-step prompts directly on the `agent` step's `params.prompt` field — no separate registry, no special-case lookup.
- **Data flow becomes explicit.** `{{steps.plan.subtasks}}` in a coder step's prompt is self-documenting. Future steps can be inserted without code changes to producers or consumers.
- **Triggers as first-class config** (Phase 2 of the overhaul) unifies the currently-scattered webhook-handler logic. A `TriggerMatcher` service replaces ad-hoc per-source template lookups in `backend/api/webhooks.py`, `webhooks_pr.py`, `webhooks_pr_comment.py`, `webhooks_slack.py`, `webhooks_discord.py`, `webhooks_linear.py`, `webhooks_monitoring.py`.
- **Workflow templates can express non-coding flows.** Monitoring response, docs updates, scheduled checks — all expressible without forking the codebase.
- **`workspace_setup` and `init` remain reliable.** Treating them as `kind: builtin` and running them as an immutable prelude means workspace_path resolution, credential injection, and branch initialization continue to be guaranteed for every run.
- **Legacy phase modules stay discoverable indefinitely.** No deletion deadline — `kind: legacy_phase` is a supported, documented step kind, not a deprecation marker with a sunset date.

### Costs

- **Frontend rewrite (Phase 3, ~12 tasks).** `WorkflowTemplates.tsx` becomes a step-composer with kind selectors. `RunDetail.tsx` gets a generic `GenericStepResult` component instead of `phaseName === "coding"` branches. `NewRun.tsx` and `PhaseTimeline.tsx` drop their hardcoded phase lists. This is real engineering work and pulls frontend capacity for the duration of the phase.
- **Docs rewrite (Phase 6, ~9 tasks).** README's "8-phase pipeline" headline goes away. `docs/WORKER_PIPELINE.md` (1558 lines) is rewritten as `docs/workflows.md` covering step kinds, triggers, templating, examples, and migration. The www marketing site's `PipelineSection.vue`, multiple blog posts, hero copy, and SEO descriptions all change. Anyone with a bookmark or external link to `worker-pipeline.md` lands on a redirect.
- **Per-phase prompt overrides become per-step prompts.** Users who have customized `RoleConfig.phase_binding` entries need their overrides re-attached to the corresponding step in the template. We will ship a one-shot migration; users who depend on the legacy binding will need to verify their templates after upgrade.
- **Implicit data-flow contracts become explicit.** The current `planning_result.subtasks → coding` chain is invisible until you read the source. Making it explicit via templating is better, but it does mean users authoring new templates have to learn the templating syntax — a small learning-curve cost.
- **Two ways to express the same workflow during the transition.** Until users migrate, the codebase will contain both legacy phase invocations and equivalent `bash`/`agent` compositions. Documentation needs to make the relationship clear and recommend the new shape for new work without telling existing users to drop everything.
- **Templating engine is new attack surface.** The hand-rolled `{{steps.NAME.field}}` substitution must not allow expression injection or shell injection through `task.title` / `task.description`. Implementation is small (~50 lines) but security review is non-negotiable.
- **External integrations reading legacy `TaskRun.*_result` columns get one release of grace.** Per the [overhaul plan](../plans/2026-05-23-agentic-workflow-overhaul.md) §"Open Questions", the legacy mirror is kept for one release after Phase 5 ships, then removed in 0.6.0. External consumers of `task_run.planning_result` etc. must migrate to reading `PhaseExecution.result` directly within that window.

## Related

- [ADR-005: Multi-Agent Pipeline](005-multi-agent-pipeline.md) — superseded by this document. Retained for historical context.
- [ADR-003: Workspace Types](003-workspace-types.md) — unchanged. `workspace_setup` remains a `kind: builtin` step.
- [ADR-006: Multi-Source Task Intake](006-multi-source-task-intake.md) — feeds into Phase 2 (triggers as first-class); the multi-source webhook handlers funnel through the new `TriggerMatcher`.
- Plan: [Agentic Workflow Overhaul](../plans/2026-05-23-agentic-workflow-overhaul.md) — the 7-phase implementation roadmap this ADR ratifies.
- Snapshot: [Current Pipeline State](../research/2026-05-23-current-pipeline-state.md) — frozen reference for the codebase shape this ADR is moving away from.

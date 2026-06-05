---
title: Direct agent selection (remove the roles abstraction)
status: accepted
date: 2026-06-05
related:
  - claudedocs/decisions/007-composable-step-workflows.md
  - claudedocs/implementations/2026-06-05-remove-roles.md
---

# 008 — Direct agent selection

## Context

Agent selection went through a **role** indirection: a workflow step requested a role
(`planner`/`coder`/`reviewer`), and `RoleResolver` mapped it to a concrete agent via
`RoleAssignment` rows with a 5-step server/global × primary/fallback cascade, plus
`RoleConfig`/`RolePromptOverride` for per-role/per-agent prompts. That design targets a
multi-server / multi-tenant fleet where the same template resolves to different agents per
machine. The actual deployment is a **single local server** with three CLI agents
(claude/codex/opencode); none of the role flexibility was used, the role/agent pickers had
already been hidden, and issue #19 tracked removing roles.

## Options considered

1. **Keep roles** — no change. Pro: nothing to do. Con: unused indirection; the agent that
   runs a step is two hops away with no per-step control; ongoing maintenance of a dead layer.
2. **Per-step `agent` field, roles as the default fallback** — additive. Pro: small, reversible.
   Con: leaves the whole role layer in place; doesn't deliver the simplification.
3. **Remove roles entirely; step names the agent, with project/global defaults** — chosen.

## Decision

The workflow step names the agent. A new `AgentResolver.resolve_agent` builds the adapter
directly from `AgentSettings`. When a step names no agent: per-project `default_agent` →
global `AgentSettings.is_default` (seeded `claude`) → `settings.default_agent`. The role
models, resolver, APIs, repos, schemas, seed, and frontend pages were deleted.

## Rationale

The indirection's three benefits (per-server agent swap, fallback chains, per-role prompt
configs) are unused on a single local box. Removing it makes "which agent runs this step"
explicit and editable in the step, deletes ~3200 lines, and matches the deprecation already
in motion.

## Consequences

- Behaviour preserved via `AgentSettings.minimal_mode` (claude) and per-phase temperature literals.
- **Irreversible**: migration `040` drops the role tables; `downgrade` is unsupported.
- Ollama is no longer an execution fallback (CLI agents only); `OllamaService` remains for
  GPU/model management.
- `PhaseExecution.agent_override` is reinterpreted as an agent name.
- Old templates carrying a `role` field still parse (ignored) and fall back to the default agent.

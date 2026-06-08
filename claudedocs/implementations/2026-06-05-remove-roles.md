---
title: Remove the roles abstraction — workflow steps name agents directly
status: implemented
date: 2026-06-05
related:
  - claudedocs/plans/2026-06-05-remove-roles.md
  - claudedocs/decisions/008-direct-agent-selection.md
---

# Remove the roles abstraction

## What was built

The role indirection (step → `role` → `RoleAssignment` → agent) is gone. A workflow step
now names an **agent** directly. Resolution order when a step runs an agent:

1. `phase_config["agent"]` (explicit per-step, set in the step editor)
2. `ProjectConfig.default_agent` (per-project default)
3. `AgentSettings.is_default` (global default, seeded `claude`)
4. `settings.default_agent` (`"claude"` constant backstop)

## Key files

| File | Change |
|------|--------|
| `backend/services/agent_resolver.py` | **New** `AgentResolver.resolve_agent` — builds the adapter from `AgentSettings` via `AdapterFactory`, no cascade |
| `backend/worker/phases/_helpers.py` | `get_phase_role` → `get_phase_agent`; `phase_uses_agent` keys off `default_agent_mode` |
| `backend/worker/phases/_prompt_resolver.py` | prompts = fallback constants + `AgentSettings.minimal_mode` + project instructions (no RoleConfig) |
| `backend/worker/phases/{planning,coding,reviewing,_comparison,_reviewing_loop}.py`, `steps/agent_step.py`, `pipeline.py` | call `agent_resolver.resolve_agent` |
| `backend/models/{agents,projects}.py` | `AgentSettings.is_default`/`minimal_mode`, `ProjectConfig.default_agent` |
| `backend/schemas/workflows.py` | `PhaseConfig.agent` field (`role` kept as ignored back-compat) |
| `frontend/src/components/workflows/stepBodies.tsx` | per-step Agent picker (claude/codex/opencode + "Default") |
| `alembic/versions/039_*`, `040_*` | add columns + seed; drop role tables |

## Removed

`RoleResolver`, `RoleAssignment`/`RoleConfig`/`RolePromptOverride` models, the role-config and
role-assignment APIs (`/api/role-configs`, `/api/role-assignments`, `/api/llm-roles`) + repos +
schemas + seed, the frontend Roles page + role API clients, and all role tests (~3200 lines net
removed across backend + frontend).

## Behaviour preserved

- **claude minimal_mode** (skip system prompt) → moved from `RolePromptOverride` to
  `AgentSettings.minimal_mode` (seeded true for claude).
- **Per-phase temperature** (planning/coding 0.3, reviewing 0.2) → kept as phase literals
  (CLI agents ignore them anyway; the per-role columns were dropped).
- **Fallback prompts** → already per-phase constants; nothing lost.

## Migration

- `039` adds the columns and seeds claude as default. `040` drops the three role tables
  (FK order; `downgrade` raises — **irreversible**). The runtime auto-migrate (`main.py`
  `_run_migrations`) does the same for installs that don't run Alembic.
- Verified on the live dev DB: columns present, claude `is_default`+`minimal_mode`, role
  tables dropped.

## Notes / limitations

- Old stored templates with a `role` field still parse (the field is ignored at runtime);
  such steps fall back to the project/global default agent.
- `PhaseExecution.agent_override` is reinterpreted as an agent name going forward.
- Ollama as an execution *fallback* is gone (CLI agents only); `OllamaService` stays for
  GPU/model management.

## Verification

- Backend suite green; frontend tsc + eslint clean, 282 tests pass.
- Mapped via a multi-agent fan-out; backend deletion + frontend deletion executed by focused
  agents with the test suites as the gate.

---
title: Remove the roles abstraction — workflow step names the agent
status: in-progress
date: 2026-06-05
related:
  - claudedocs/decisions/007-composable-step-workflows.md
---

# Remove the roles abstraction

## Goal

Eliminate the role indirection (role → `RoleAssignment` → agent). A workflow step names the
**agent** directly; when it doesn't, a **per-project default** (`ProjectConfig.default_agent`)
or the **global default** (`AgentSettings.is_default`, seeded `claude`) runs.

## Decisions (locked)

- **Default agent**: `claude` (global). Resolution order for a step:
  `phase_config["agent"]` → `ProjectConfig.default_agent` → `AgentSettings.is_default` →
  `settings.default_agent` constant (`"claude"`).
- **Scope**: global default (`AgentSettings.is_default`) **and** per-project override
  (`ProjectConfig.default_agent`, new nullable column).
- **temperature/num_predict**: dropped — the CLI agents (claude/codex/opencode) ignore them;
  phases keep their literal defaults in the `generate()` call.
- **minimal_mode** (claude skips system prompt): moved to `AgentSettings.minimal_mode` (seed claude=True).
- **Legacy `role` field**: ignored (no data migration); seeded templates switch to agent/default.
- **Ollama settings-default fallback**: dropped (CLI agents only; `OllamaService` stays for GPU/model mgmt).
- **Migrations**: keep history (003/005); add a drop migration LAST. `downgrade` is a no-op (irreversible).

## Replacement

- New `backend/services/agent_resolver.py`: `AgentResolver.resolve_agent(agent_name, session, ws_id, project_id)`
  → `ResolvedAgent(adapter, agent_settings)`. Builds the adapter via the existing
  `AdapterFactory.create_agent_adapter` (same code path RoleResolver used), no cascade.
- `get_phase_agent` in `_helpers.py` (mirrors `get_phase_role`): `phase_config["agent"]` else None
  (resolver fills the project/global/constant default).
- `resolve_prompts` gains an agent-name path: prompts from phase fallback constants + step params +
  project instructions; `minimal_mode` from `AgentSettings`.

## Phases (verify gate after each)

1. **Introduce (additive)** — add `AgentSettings.is_default`/`minimal_mode`, `ProjectConfig.default_agent`
   (+ migration + main.py runtime auto-migrate); `agent_resolver.py`; container/dependencies wiring;
   `agent` field on `PhaseConfig`; `get_phase_agent`; `default_agent` in `PHASE_META`/registry;
   agent-name path in `resolve_prompts`; seed claude `is_default`/`minimal_mode`. Old path untouched.
2. **Migrate call sites** — the 7 `role_resolver.resolve` sites (`agent_step`, `planning`, `coding`,
   `reviewing`, `_comparison`, `_reviewing_loop`, `pipeline`) → `agent_resolver`; drop `role_config`
   consumption; templates use `agent`. `mock_services` gains `agent_resolver`. Roles now unused at runtime.
3. **Delete backend role machinery** — APIs (`llm_roles`, `role_configs`), repos, `role_resolver`,
   models (`roles.py`, `RoleConfig`/`RolePromptOverride`), schemas, seed, backup registry, runtime
   auto-migrate create-block; delete orphaned role tests; fix seed/export/import tests.
4. **Delete frontend role machinery** — role pages/types/api/routes; add agent picker to the step editor.
5. **Drop migration last** — drop `role_prompt_overrides`/`role_configs`/`role_assignments`; ADR + log.

## Success criteria

- [ ] A workflow step with `agent: "codex"` runs codex; without it, project/global default (`claude`).
- [ ] Per-project `default_agent` overrides the global default.
- [ ] claude `minimal_mode` preserved; phases still run planning/coding/reviewing + comparison + consolidated.
- [ ] No runtime reference to roles; role tables dropped; fresh + existing DB migrate cleanly.
- [ ] ruff + pyright clean; full backend + frontend suites green.

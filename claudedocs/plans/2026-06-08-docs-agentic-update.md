---
title: Bring public docs and skills in line with the agentic model
status: planned
date: 2026-06-08
related:
  - claudedocs/plans/2026-06-05-remove-roles.md
  - claudedocs/decisions/008-direct-agent-selection.md
  - claudedocs/decisions/007-composable-step-workflows.md
  - docs/plans/2026-03-22-website-readme-update-design.md
---

# Docs & Site Agentic Update

## Goal

Update all public-facing and internal documentation — root README, CLAUDE.md, `.claude/skills/`, and the `agentickodeweb` marketing site — so every mention of the removed "roles" abstraction and the stale "8-phase pipeline as the primary model" framing is replaced with the current agentic model: a user gives a prompt, an agent runs automatically to completion (similar to Paperclip), with the composable-step workflow as the underlying engine.

## Scope

### In scope
- `README.md` (root) — remove/rewrite stale roles/RoleAdapter/8-phase framing
- `CLAUDE.md` — update Overview + Key Features + Architecture Rules + Worker Pipeline sections
- `.claude/skills/autodev-run/SKILL.md` — drop "8 phases" bullet
- `.claude/skills/dev-flow/references/req-analyzer.md` — drop 8-phase pipeline line + RoleAdapter line
- `.claude/skills/dev-flow/references/arch-planner.md` — drop RoleAdapter/RoleResolver line
- `.claude/skills/dev-flow/references/implementer.md` — drop RoleAdapter Protocol line
- `.claude/skills/dev-flow/references/reviewer.md` — drop RoleAdapter check
- `.claude/skills/dev-flow/references/plan-reviser.md` — drop RoleAdapter line
- `.claude/skills/plan/SKILL.md` — two RoleAdapter references in template
- `agentickodeweb` marketing site — full content pass (Part B)

### Out of scope
- `docs/workflows.md` — intentionally retained as the authoritative technical reference; `role` field in the `agent` step kind is now just a legacy label, not backed by RoleResolver; note should be added but the doc is otherwise accurate
- `docs/WORKER_PIPELINE.md` — already marked deprecated; leave as-is
- `claudedocs/decisions/` ADRs — historical records, should not be rewritten
- Test files, migration files, source code
- The companion "workflows-to-flow-prompts" refactor (separate plan/feature)

---

## Part A — This repo (actionable now)

### Stale references found (grounded in actual file inspection)

| File | Line(s) | Stale text | What to change |
|------|---------|------------|----------------|
| `README.md` | 7 | Tagline: "Composable AI workflows triggered by your tools" | Reframe: agentic — agent gets a prompt and runs; workflows are an implementation detail |
| `README.md` | 36–37 | `*Full UI walkthrough — Dashboard, … Workflows, Settings*` (image caption) | Caption fine; "Workflows" UI still exists, keep |
| `README.md` | 42 | "Composable `bash` + `agent` steps…" (first Why bullet) | Reframe to agentic framing first; keep technical detail as secondary |
| `README.md` | 79 | `agent` step kind description: "Invokes a role (planner / coder / reviewer / custom) through `RoleResolver` with a rendered prompt." | Remove RoleResolver mention; roles were deleted. Rewrite: step invokes an agent directly (per-step `agent` field or project default). |
| `README.md` | 108 | "The **RoleAdapter Protocol** lets you plug in any AI agent" | Rename to "AgentAdapter Protocol" or just "plugin architecture"; RoleAdapter was deleted |
| `README.md` | 136 | "These are used for text generation roles (planner, reviewer)" | Remove "roles" framing; they are agents used for specific steps |
| `README.md` | 147 | "Implement the `RoleAdapter` Protocol (4 methods…) and register in the `AdapterFactory`." | Update to current API: implement `AgentAdapter` / `CliAgentAdapter` and register |
| `README.md` | 152–157 | Code block: `agent[role: planner]`, `agent[role: coder]`, `agent[role: reviewer]` | Update example: steps now use `agent: "ollama"` / `agent: "claude_cli"` directly, not roles |
| `README.md` | 255 | "Role assignment — assign specific servers and models to roles (planner, coder, reviewer, custom)" | Remove; Ollama server management no longer maps to roles |
| `README.md` | 333 | Design Principles: "`GitProvider` and `RoleAdapter` Protocols make everything pluggable" | Replace `RoleAdapter` → `AgentAdapter` (or whatever the current protocol name is) |
| `CLAUDE.md` | 5 | "The backend runs an 8-phase worker pipeline (workspace_setup → init → …)" | Replace with: composable-step workflow engine; legacy pipeline still runs via `default` template |
| `CLAUDE.md` | 25 | "**Pluggable AI agents**: … (via RoleAdapter Protocol)" | Replace "RoleAdapter Protocol" → "AgentAdapter Protocol" |
| `CLAUDE.md` | 26 | "**8-phase worker pipeline**: With per-phase status tracking…" | Replace: composable step workflow with configurable steps; trigger modes still valid |
| `CLAUDE.md` | 28 | "**Workflow templates**: Label-based routing with per-phase agent/role configuration" | Update: "per-phase agent/role configuration" → "per-step agent selection" |
| `CLAUDE.md` | 36 | "**Role configs**: Customizable roles (planner, coder, reviewer) with per-agent prompt overrides" | Remove entirely — roles were deleted (ADR-008) |
| `CLAUDE.md` | 53 | `worker/   # Worker engine + 8-phase pipeline` | Update comment to: "Worker engine + composable step runner" |
| `CLAUDE.md` | 149 | Arch Rule 2: "Use `RoleResolver` to map roles to providers. Never call agent APIs directly." | Replace: use `AgentResolver` (the replacement) and `get_phase_agent()`. Never call agent APIs directly. |
| `CLAUDE.md` | 218 | Worker Pipeline section: "8 phases: workspace_setup → init → planning → coding → testing → reviewing → approval → finalization" | Reframe: worker runs templates; `default` template still has those steps as `legacy_phase` kind |
| `.claude/skills/autodev-run/SKILL.md` | 3 | description: "running the 8-phase pipeline" | Replace with: "dispatching an agentic run" |
| `.claude/skills/autodev-run/SKILL.md` | 105 | "The 8 phases are: workspace_setup, init, planning, coding, testing, reviewing, approval, finalization" | Remove or replace: "Step names depend on the workflow template. The default template still uses these step names." |
| `.claude/skills/dev-flow/references/req-analyzer.md` | 1 | "…with an 8-phase worker pipeline" | Replace with: "…with a composable-step workflow engine" |
| `.claude/skills/dev-flow/references/req-analyzer.md` | 16–17 | "RoleAdapter Protocol (AI agents)" + "Worker pipeline: 8 phases …" | Drop RoleAdapter; replace pipeline line with composable workflow description |
| `.claude/skills/dev-flow/references/arch-planner.md` | 15 | "**RoleAdapter Protocol**: All AI agent interactions through Protocol. Use `RoleResolver` for mapping." | Replace: "**AgentAdapter Protocol**: All AI agent interactions through the adapter. Use `AgentResolver`." |
| `.claude/skills/dev-flow/references/implementer.md` | 36 | "AI agent ops: Through `RoleAdapter` Protocol only" | Replace with AgentAdapter |
| `.claude/skills/dev-flow/references/reviewer.md` | 18 | "AI agent ops use `RoleAdapter` Protocol — no direct calls" | Replace with AgentAdapter |
| `.claude/skills/dev-flow/references/plan-reviser.md` | 9 | "GitProvider/RoleAdapter Protocols for extensibility" | Replace RoleAdapter → AgentAdapter |
| `.claude/skills/plan/SKILL.md` | 42 | "Which Protocols to implement/use (GitProvider, RoleAdapter, etc.)" | Replace RoleAdapter → AgentAdapter |
| `.claude/skills/plan/SKILL.md` | 57 | "Use existing Protocols (GitProvider, RoleAdapter) — never call APIs directly" | Replace RoleAdapter → AgentAdapter |

### New framing to adopt (for README and CLAUDE.md rewrite)

The product framing has shifted to **fully agentic**:
- A user (or webhook/cron) provides a prompt describing a task
- AgenticKode picks a workspace, runs the workflow template end-to-end, and delivers a PR — no manual steps unless a `wait_for_approval` gate is configured
- The "Paperclip" analogy: once started, the agent drives the task to completion autonomously
- "Workflows" / "templates" are the _implementation_ detail, not the top-level pitch
- The old 8-phase pipeline still works (as the `default` template) — no need to hide it, but it should not lead the docs

### README.md section rewrites (summary)

| Section | Action |
|---------|--------|
| Tagline (line 5) | Rewrite to agentic framing: "Give it a task, an agent delivers the PR" |
| Why AgenticKode (line 37+) | Lead with agentic autonomy; move composable-steps bullet to second position |
| "How It Works" (line 52+) | Replace with agentic flow diagram: prompt → template → workspace → agent runs → PR |
| Step Kinds table — `agent` row | Remove RoleResolver; describe direct agent selection |
| "Bring Your Own Agent" section | Replace `RoleAdapter` with current protocol name |
| "Mix & Match" example | Update code block to use `agent:` field directly |
| Ollama features bullet | Remove "role assignment" sub-bullet |
| Design Principles | Replace `RoleAdapter` → `AgentAdapter` |

### CLAUDE.md section rewrites (summary)

| Section | Action |
|---------|--------|
| Overview (line 5) | Replace 8-phase pipeline sentence with composable workflow description |
| Key Features (lines 25–36) | Update RoleAdapter → AgentAdapter; remove "Role configs" bullet; update "8-phase" bullet |
| Project Structure comment (line 53) | Update `worker/` comment |
| Architecture Rule 2 (line 149) | Replace RoleResolver/RoleAdapter with AgentResolver/AgentAdapter |
| Worker Pipeline section (line 218) | Clarify default template; remove implied "these are the only phases" |

---

## Part B — agentickodeweb (requires cloning the other repo)

The marketing site repo is at `https://github.com/mechemsi/agentickodeweb` (Nuxt 4 + Vue 3, `@nuxt/content` v3). It was NOT inspectable during this planning session. The following changes are inferred from the task description and the prior plan at `docs/plans/2026-03-22-website-readme-update-design.md`.

### How to get the repo

```bash
git clone https://github.com/mechemsi/agentickodeweb.git
cd agentickodeweb
```

### Content areas likely needing updates (verify after cloning)

| Area | Expected stale content | Required change |
|------|----------------------|-----------------|
| Hero section (`HeroSection.vue` or content equivalent) | "Composable workflows triggered by your tools" tagline | Reframe to agentic: "Give it a task. An agent delivers the PR." |
| How it works / pipeline diagram | Shows 8-phase pipeline as primary model | Replace with agentic flow: prompt → template → agent → PR. Mention template flexibility as a secondary point. |
| Features section | "Workflow templates", "Role configs", possibly "8-phase pipeline" | Remove "Role configs" card (deleted). Update "Workflow templates" card to reflect direct agent selection. |
| "Two modes" or pipeline/autonomous section | If the 2026-03-22 design was implemented, there's a `LandingModesSection.vue` with "Pipeline Mode" and "Autonomous Mode" as equals | Collapse into single agentic model; remove the pipeline vs. autonomous dichotomy |
| Agents section | May reference "roles (planner, coder, reviewer)" framing | Replace with: agents are assigned per step in a template, or as a project default |
| Any "update" / workflow-specific copy | General references to "updating code via structured workflow" | Replace with: "agent receives a prompt and runs autonomously" |
| Documentation / changelog pages | May reference roles or old pipeline | Audit and remove stale entries |

### Suggested content blocks for the site (new framing)

**Hero tagline options:**
- "Give it a task. An agent delivers the PR."
- "AI agents that work like a developer, not a chatbot."
- "Prompt in, pull request out — fully automated, self-hosted."

**How it works (3-step)**:
1. A trigger fires (issue, webhook, cron, or manual) — AgenticKode picks the right template
2. A workspace is set up and an agent receives the rendered prompt
3. The agent works autonomously: plans, codes, tests, opens a PR — with optional human-approval gates

**Key differentiators to keep on site:**
- Self-hosted, private (code never leaves your infra)
- 7+ AI agents, auto-installed on workspace servers
- Trigger-driven: GitHub/GitLab/Gitea/Plane/Notion/cron
- Human-in-the-loop as an optional gate, not a requirement

---

## Technical Approach

- Part A is pure documentation editing — no code changes
- All README/CLAUDE.md edits are in-place rewrites of specific lines (listed in the table above)
- All skill edits are targeted one-line or one-sentence replacements
- Part B requires cloning `agentickodeweb` and doing a content pass with Nuxt/Vue knowledge; the `@nuxt/content` v3 pages are likely in `content/` as Markdown or in `components/` as Vue SFCs

---

## Success Criteria

- [ ] `README.md`: No remaining mentions of `RoleAdapter`, `RoleResolver`, or `role: planner/coder/reviewer` as a routing concept
- [ ] `README.md`: Top-level framing leads with agentic autonomy, not "composable workflows"
- [ ] `CLAUDE.md`: Overview paragraph describes composable workflow engine, not "8-phase pipeline"
- [ ] `CLAUDE.md`: "Role configs" bullet removed; `RoleAdapter` → `AgentAdapter` in Architecture Rules
- [ ] `CLAUDE.md`: Worker Pipeline section clarified as "default template" behavior
- [ ] All 6 `dev-flow/references/*.md` files: `RoleAdapter`/`RoleResolver` references replaced with `AgentAdapter`/`AgentResolver`
- [ ] `autodev-run/SKILL.md`: No "8-phase pipeline" in description or notes
- [ ] `plan/SKILL.md`: Both `RoleAdapter` references replaced
- [ ] `agentickodeweb`: Hero tagline reflects agentic model
- [ ] `agentickodeweb`: No "Role configs" or "roles (planner/coder/reviewer)" in feature cards
- [ ] `agentickodeweb`: "How it works" shows prompt → agent → PR, not phase-by-phase walkthrough

---

## Risks / Open Questions

| Risk | Notes |
|------|-------|
| Current protocol name | `RoleAdapter` was deleted per ADR-008. The replacement appears to be an `AgentAdapter`-style concept. Verify the exact current protocol/class name in `backend/services/adapters/` before editing |
| `docs/workflows.md` accuracy | The `agent` step kind still documents `role:` as a field (line 132: `role: coder`). This is now just a label, not routed through RoleResolver. A short deprecation note should be added to that table row — but this doc is otherwise correct and need not be fully rewritten |
| agentickodeweb structure | Cannot verify page/component file paths without cloning. The 2026-03-22 design plan exists but it's unclear how much of it was implemented |
| "workflows-to-flow-prompts" companion feature | Task description mentions this as a separate but related initiative. If that refactor renames the `WorkflowTemplate` model or the UI, the README and site content will need another pass afterward. Coordinate timing. |
| README screenshot alt text | Line 162: `alt="Workflow Templates"` — still valid if the UI page is still named "Workflows". Verify before changing. |

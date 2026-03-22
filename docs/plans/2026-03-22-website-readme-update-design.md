# Website & README Update Design

## Date: 2026-03-22

## Goal
Update the www landing page and README.md to reflect all new features since initial release, especially the shift from "pipeline-only" to "pipeline + autonomous" dual-mode platform.

## Positioning
Both pipeline mode and autonomous mode are first-class workflows — presented as equals.

## Website Changes

### HeroSection.vue
- **Subtitle**: "Dispatch tasks to AI agents that work autonomously or through a structured 8-phase pipeline — with human approval gates."
- **Terminal animation**: Two sequences cycling (~8s each, ~18s total):
  1. Pipeline mode (current): `$ agentickode run --task "Add JWT auth"` → phases tick through
  2. Autonomous mode (new): `$ agentickode run --mode autonomous --task "Refactor API layer"` → context analysis, working, PR opened
- **Terminal bar label** alternates between modes

### New: LandingModesSection.vue (between Hero and Pipeline)
- Header: "Two ways to ship"
- Subtitle: "Choose structured pipeline control or let agents work autonomously — or combine both."
- Two side-by-side glass cards:
  - **Pipeline Mode** (cyan): 8 phases, per-phase control, live streaming. Bullets: per-phase agent selection, comparison mode, webhook triggers.
  - **Autonomous Mode** (violet): Agent works independently, opens PR. Bullets: context-aware planning, configurable autonomy level, direct PR creation.

### FeaturesSection.vue (6 cards, updated)
1. **Multi-Provider Git** — keep as-is
2. **Pluggable AI Agents** — update to 7 CLI agents, mention Codex/Gemini/Aider/etc.
3. **Two Workflow Modes** (NEW, replaces Workflow Templates) — violet, pipeline + autonomous + templates
4. **Smart Workspaces** (NEW, replaces Remote Workspaces) — multi-workspace, server groups, load balancing, persistent sessions
5. **Real-Time Streaming** — add terminal user selection, persistent tmux sessions
6. **Cost Tracking** — keep as-is

### PipelineSection.vue
- Subtitle: "In pipeline mode, every task flows..." (prefix added)
- Sub-cards stay as-is

### StatsSection.vue
- "3+ AI Agents" → "7+ CLI Agents"
- Chart bars: Claude, Codex, Gemini, Aider (was Claude, Ollama, OpenHands, Custom)

### index.vue
- Add `<LandingModesSection />` between HeroSection and PipelineSection

## README.md Changes

### Updated sections:
- Subtitle paragraph adds dual-mode mention
- "Why AgenticKode" adds "Two workflow modes" bullet
- "How It Works" adds mode intro table before pipeline diagram
- Features: new subsections for Multi-Workspace, Persistent CLI Sessions, Autonomous Mode
- Workspace Management: add server groups, Docker management, terminal user selection
- Project Structure: update counts (27 migrations, 47+ components)
- Agent count: already current with 7 CLI agents
- Roadmap: mark completed items

### New subsections:
- Multi-Workspace & Load Balancing
- Persistent CLI Sessions
- Autonomous Mode

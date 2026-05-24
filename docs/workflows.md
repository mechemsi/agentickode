# AgenticKode Workflows — Composable Step Reference

> **What changed:** the framework no longer ships a single fixed 8-phase pipeline as its only execution model. Workflows are now composable arrays of steps. Each step is either a `bash` command or an `agent` invocation with a rendered prompt. Two built-in steps (`workspace_setup`, `init`) always run first; the rest is per-template. This document is the authoritative reference for the new model.
>
> See [ADR-007 — Composable Step Workflows](../claudedocs/decisions/007-composable-step-workflows.md) for the design rationale and trade-offs against the legacy fixed-phase model.

---

## Table of Contents

1. [Overview](#overview)
2. [Step Kinds](#step-kinds)
3. [Shared Step Rules](#shared-step-rules)
4. [Built-in Prelude: `workspace_setup` + `init`](#built-in-prelude-workspace_setup--init)
5. [Templating](#templating)
6. [Triggers](#triggers)
7. [Workspace Strategies](#workspace-strategies)
8. [Migrating from the Legacy Pipeline](#migrating-from-the-legacy-pipeline)
9. [API Endpoints](#api-endpoints)
10. [Examples](#examples)

---

## Overview

A **workflow template** is a row in `WorkflowTemplate` with three meaningful fields for execution:

| Field | Type | Purpose |
|-------|------|---------|
| `phases` | `list[PhaseConfig]` (JSONB) | Ordered list of steps. The field name predates the rewrite — read it as "steps". |
| `triggers` | `list[WorkflowTriggerRule]` (JSONB) | Declarative rules that auto-fire this workflow on events. |
| `label_rules` | `list[LabelRule]` (JSONB) | Legacy label routing. Backfilled into `triggers[type=label]` by Alembic 037; keep using `triggers` for new templates. |

A run dispatched to a template executes:

```
workspace_setup  (builtin)
  → init         (builtin)
  → step 1       (bash | agent | legacy_phase)
  → step 2       (bash | agent | legacy_phase)
  → ...
```

Every step's result is persisted to `PhaseExecution.result` (JSONB), and later steps reference those results via `{{steps.NAME.field}}` templating.

### Minimal example

A template that builds the project, then asks an agent to add a feature, then runs tests:

```json
{
  "name": "build-feature-test",
  "triggers": [{"type": "label", "match_any": ["feature"]}],
  "phases": [
    {
      "phase_name": "build",
      "kind": "bash",
      "params": {"command": "make build"},
      "timeout_seconds": 600
    },
    {
      "phase_name": "implement",
      "kind": "agent",
      "role": "coder",
      "params": {
        "prompt": "Implement: {{run.title}}\n\nContext:\n{{run.description}}",
        "mode": "task"
      },
      "timeout_seconds": 3600
    },
    {
      "phase_name": "verify",
      "kind": "bash",
      "params": {"command": "pytest -x"},
      "failure_mode": "fail"
    }
  ]
}
```

---

## Step Kinds

All steps are `PhaseConfig` rows with a `kind` discriminator. Each kind reads a different `params` shape but shares the [Shared Step Rules](#shared-step-rules) (timeout, retry, failure mode, trigger mode).

### `bash`

Runs a shell command on the workspace server via `CommandExecutor`. Captures stdout, stderr, and exit code.

**Params:**

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `command` | string | yes | Shell command. Supports `{{run.X}}` and `{{steps.NAME.FIELD}}` substitution. |

**Output (written to `PhaseExecution.result`):**

```json
{
  "command": "<rendered command>",
  "stdout": "...",
  "stderr": "...",
  "exit_code": 0,
  "skipped": false
}
```

On non-zero exit:
- `failure_mode: "fail"` (default) → raises `RuntimeError`, step is marked failed.
- `failure_mode: "skip"` → returns `result.skipped = true`, workflow continues.

**Implementation:** `backend/worker/steps/bash_step.py` (`run_bash_step`). Default timeout `600s`.

### `agent`

Resolves a role to a concrete adapter via `RoleResolver` and invokes the agent with a rendered prompt.

**Params:**

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `prompt` | string | yes | — | Instruction sent to the agent. Templating supported. |
| `mode` | enum | no | `generate` | `generate` → `adapter.generate(prompt)`; `task` → `adapter.run_task(workspace, prompt)`. `task` mode requires `task_run.workspace_path` to be set. |
| `session_id` | string | no | — | CLI session id (e.g. Claude `--resume`). |
| `new_session` | bool | no | `false` | Force a fresh session even if a previous one exists. |

**Top-level keys (on the step itself, not in `params`):**

| Key | Type | Description |
|-----|------|-------------|
| `role` | string | The role to resolve. Defaults to `coder`. Common values: `planner`, `coder`, `reviewer`, or any role you've registered. |
| `agent_override` | string | Force a specific adapter (e.g. `claude_cli`) regardless of role config. |
| `cli_flags` | dict | Per-step CLI flags forwarded to the adapter. |
| `environment_vars` | dict | Per-step env vars forwarded to the adapter. |

**Output:**

```json
{
  "provider": "claude_cli",
  "role": "coder",
  "mode": "task",
  "prompt": "<rendered prompt>",
  "response": "<str for generate, dict for task>",
  "session_id": "<set by adapter when task mode returns one>"
}
```

**Implementation:** `backend/worker/steps/agent_step.py` (`run_agent_step`). Default timeout `1800s`.

### `legacy_phase`

Invokes one of the original domain modules from `backend/worker/phases/`. The phase registry auto-discovers any module exporting `run()` and a `PHASE_INFO` constant; the modules below are the discoverable set as of 0.5.0:

| Module | Description |
|--------|-------------|
| `planning` | Decompose the task into ordered subtasks (writes `planning_result.subtasks`). |
| `coding` | Iterate subtasks; invoke the `coder` role per subtask. |
| `testing` | Run the configured test command on the workspace. |
| `reviewing` | Invoke the `reviewer` role on the diff produced by `coding`. |
| `approval` | Push the branch, create a PR, park the run with `trigger_mode: wait_for_approval`. |
| `finalization` | Send notifications, merge if configured, clean up the workspace. |
| `pr_fetch` | Fetch a PR's metadata + diff into the task run (used by PR-review templates). |
| `task_creation` | Create an upstream issue/task in the configured task source. |
| `agent_loop` | Long-running autonomous-mode driver (episodic execution with checkpoints). |

**Deprecation status:** kept indefinitely for back-compat. The `default` seeded template is composed entirely of `legacy_phase` steps. There is no sunset date. New templates should prefer `bash` and `agent` steps unless they need a legacy module's specific machinery (e.g. `approval`'s PR-park-and-resume mechanic).

---

## Shared Step Rules

Every step kind reads the following fields from its `PhaseConfig` entry:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `phase_name` | string | required | Unique identifier within the workflow. Used as the `{{steps.NAME.field}}` lookup key. |
| `kind` | `bash` \| `agent` \| `legacy_phase` | `legacy_phase` | Step type discriminator. |
| `enabled` | bool | `true` | If false, the step is skipped entirely. |
| `timeout_seconds` | int | `600` (bash) / `1800` (agent) / per-module (legacy) | Hard timeout for the step. |
| `trigger_mode` | string | `auto` | `auto` runs immediately; `wait_for_trigger` parks the run for manual advancement; `wait_for_approval` parks for human approval. |
| `failure_mode` | `fail` \| `skip` | `fail` | On error, fail the run or skip the step and continue. |
| `notify_source` | bool | `false` | If true, the configured `TaskSourceUpdater` is called when the step completes. |
| `params` | dict | `{}` | Kind-specific parameters (see each kind above). |
| `role` | string | `coder` for `agent` | Role name resolved by `RoleResolver`. |
| `agent_override` | string | none | Force a specific adapter regardless of role config. |
| `cli_flags` | dict | none | Per-step CLI flags forwarded to adapters. |
| `environment_vars` | dict | none | Per-step env vars. |
| `command_templates` | dict | none | Per-step command template overrides (used by `legacy_phase` steps that emit shell commands). |

---

## Built-in Prelude: `workspace_setup` + `init`

These two steps **always run first** and are not user-composable. They are tagged `kind: builtin` in the phase registry and the workflow engine prepends them to every template at execution time.

| Step | Responsibility |
|------|----------------|
| `workspace_setup` | Clone the repo (or pull latest), checkout/create a feature branch named after the run, set up worktree if `workspace_strategy: worktree`, inject credentials. Writes `task_run.workspace_path`. |
| `init` | Walk the project tree, detect languages and frameworks, build a context summary, load project-level instructions and secrets. Result is exposed to later steps as `{{steps.init.context_summary}}`. |

Why immutable? `workspace_path` must be set before any `bash` or `agent[mode=task]` step runs, and the context summary is the only mechanism that injects project-level instructions into agent prompts. Making them user-configurable risked accidental misconfiguration breaking every run.

---

## Templating

Steps support `{{...}}` substitution in any string-valued field (`params.command`, `params.prompt`, etc.). The grammar is deliberately tiny — no Jinja, no eval, no shell interpolation. Two patterns:

### `{{run.FIELD}}`

Reads `getattr(task_run, FIELD, "")`. `None` becomes `""`. Common fields:

| Placeholder | What you get |
|-------------|--------------|
| `{{run.title}}` | The task title (e.g. issue title). |
| `{{run.description}}` | The task description / issue body. |
| `{{run.task_id}}` | Upstream task identifier (e.g. `gh-1234`). |
| `{{run.id}}` | Internal run id (int). |
| `{{run.workspace_path}}` | Absolute path on the workspace server after `workspace_setup`. |

### `{{steps.NAME.FIELD}}`

Reads the latest **completed** `PhaseExecution` for step `NAME` and looks up `result[FIELD]`. If the step hasn't completed or the field is missing, substitutes `""` and logs a warning.

```text
{{steps.plan.subtasks}}       → result["subtasks"] of the most recent completed `plan` step
{{steps.build.stdout}}        → stdout of the most recent completed `build` bash step
{{steps.review.response}}     → the agent's review response text
```

### Worked example

```json
{
  "phases": [
    {
      "phase_name": "plan",
      "kind": "agent",
      "role": "planner",
      "params": {
        "prompt": "Plan the work for: {{run.title}}\n\nDescription:\n{{run.description}}"
      }
    },
    {
      "phase_name": "code",
      "kind": "agent",
      "role": "coder",
      "params": {
        "prompt": "Implement the plan below:\n\n{{steps.plan.response}}",
        "mode": "task"
      }
    },
    {
      "phase_name": "summarize",
      "kind": "bash",
      "params": {
        "command": "echo 'Run {{run.id}} produced session {{steps.code.session_id}}' >> /tmp/runlog"
      }
    }
  ]
}
```

**Security:** the templating engine is intentionally non-Turing-complete and does not invoke a shell to expand placeholders. Substituted values are still passed into `command` as part of a shell string, so the same shell-quoting hygiene that applies to any user-supplied string applies here. Treat `task.title` / `task.description` as untrusted input when authoring bash commands.

Implementation: `backend/worker/steps/templating.py` (~60 lines).

---

## Triggers

A template's `triggers[]` array declares when the workflow auto-fires. Webhooks from GitHub, Gitea, GitLab, Plane, and Notion, plus the schedule poller, funnel through a single `TriggerMatcher` service that routes the event to whichever templates match.

Five trigger types are defined in `backend/schemas/workflows.py`:

### `label`

Match by label/tag set. Equivalent to the legacy `label_rules` mechanism but with a source filter.

```json
{"type": "label", "source": "any", "match_any": ["bug", "regression"]}
{"type": "label", "source": "github", "match_all": ["security", "p0"]}
```

| Field | Description |
|-------|-------------|
| `source` | `github`, `gitea`, `gitlab`, `plane`, `notion`, or `any`. |
| `match_all` | All listed labels must be present. |
| `match_any` | At least one listed label must be present. |

### `issue_event`

Match issue lifecycle events on supported sources.

```json
{"type": "issue_event", "source": "github", "action": "opened"}
{"type": "issue_event", "source": "any", "action": "labeled", "label_filter": ["bug"]}
```

| Field | Description |
|-------|-------------|
| `source` | `github`, `gitea`, `gitlab`, `plane`, `notion`, or `any`. |
| `action` | `opened`, `labeled`, `commented`, or `any`. |
| `label_filter` | ANDed with the action match when non-empty. |

### `pr_event`

Match pull/merge-request events.

```json
{"type": "pr_event", "source": "github", "action": "review_requested"}
{"type": "pr_event", "source": "any", "action": "comment", "label_filter": ["needs-review"]}
```

| Field | Description |
|-------|-------------|
| `source` | `github`, `gitea`, `gitlab`, or `any`. |
| `action` | `opened`, `review_requested`, `labeled`, `comment`, or `any`. |

### `schedule`

Fire on a cron schedule. Evaluated by the scheduled-trigger poller (see [Scheduled trigger executor](../claudedocs/implementations/) commit history).

```json
{"type": "schedule", "cron": "0 * * * *"}        // every hour on the hour
{"type": "schedule", "cron": "*/15 * * * *"}     // every 15 minutes
```

Standard 5-field cron expression. The poller checks templates every minute and dispatches a new run for any template whose cron crosses the current tick.

### `manual`

Sentinel — never matches an external event. Use to mark templates that should only be dispatched via `POST /api/runs` with an explicit `workflow_template_id`.

```json
{"type": "manual"}
```

---

## Workspace Strategies

A template (or a per-run override) selects how `workspace_setup` lays out the working directory:

| Strategy | What it does | When to use |
|----------|--------------|-------------|
| `shared_clone` (default) | Maintain one clone per project on the workspace server. Each run checks out its feature branch in the shared directory. | Default. Lower disk usage. Acceptable when you don't run concurrent jobs on the same project. |
| `worktree` | Per-run isolated worktree at `<project_root>/.worktrees/run-<run_id>-<timestamp>/` on the workspace server. | Concurrent runs on the same project. Inspired by the myDash worktree pattern — pure-function naming, idempotent create/remove, timestamped to avoid collisions. |

Set per-template under `phases[0].params.workspace_strategy` (the `workspace_setup` step), or per-run via the API. Worktree cleanup runs automatically on `finalization` and is also swept by a scheduled job for orphans.

Implementation: `backend/services/workspace/worktree.py` (pure path functions + `WorktreeManager`).

---

## Migrating from the Legacy Pipeline

The legacy 8-phase pipeline (`workspace_setup → init → planning → coding → testing → reviewing → approval → finalization`) is preserved verbatim as the `default` seeded template — every step has `kind: legacy_phase` and the modules in `backend/worker/phases/` are unchanged. Nothing forces you to migrate.

When you do want to compose your own workflow, here's the equivalent recipe for each legacy phase using generic step kinds:

| Legacy phase | Composable equivalent |
|--------------|----------------------|
| `planning` | `{kind: agent, role: planner, params: {prompt: "Plan: {{run.title}}\n\n{{run.description}}"}}` |
| `coding` | `{kind: agent, role: coder, params: {prompt: "Implement: {{steps.plan.response}}", mode: "task"}}` |
| `testing` | `{kind: bash, params: {command: "make test"}}` (or `pytest`, `npm test`, etc.) |
| `reviewing` | `{kind: agent, role: reviewer, params: {prompt: "Review the diff and report issues."}}` |
| `approval` | Any step with `trigger_mode: wait_for_approval` (parks the run; a human approves via UI or API). |
| `finalization` | `{kind: bash, params: {command: "gh pr merge --auto --squash"}}` (or whatever your post-merge ritual is). |

The `approval` and `finalization` legacy modules also encapsulate non-trivial behavior (PR creation + approval-timeout parking; notifications + worktree cleanup) — keep using them as `legacy_phase` steps if you want that machinery for free.

### Per-step prompt overrides

Before ADR-007, per-phase prompt overrides lived in `RoleConfig.phase_binding`. They still work for `legacy_phase` steps. For `agent` steps, put the prompt directly in `params.prompt` — no separate registry, no special-case lookup.

---

## API Endpoints

### `GET /api/step-kinds`

Returns the composable step kinds the workflow builder can use, with per-kind `params_schema` describing required and optional fields. Drives the frontend step editor.

```bash
curl http://localhost:8000/api/step-kinds
```

Response shape (abbreviated):

```json
[
  {"kind": "bash", "description": "...", "params_schema": {"command": {...}}},
  {"kind": "agent", "description": "...", "params_schema": {"prompt": {...}, "mode": {...}, ...}},
  {"kind": "legacy_phase", "description": "...", "values": ["planning", "coding", ...]}
]
```

### `GET /api/phases`

Returns all discovered phase modules (the values addressable by `kind: legacy_phase`) plus their metadata (`default_role`, `default_agent_mode`, `deprecated_in`). Drives the frontend's legacy-phase picker.

### `POST /api/workflow-templates/{id}/dry-run`

Tests whether a synthetic event would fire a template's triggers. Returns `matched`, the template (when matched), and a human-readable `reason` like `"matched trigger #2 (LabelTrigger source=github)"`.

```bash
curl -X POST http://localhost:8000/api/workflow-templates/3/dry-run \
  -H "Content-Type: application/json" \
  -d '{
    "type": "issue_event",
    "source": "github",
    "action": "opened",
    "labels": ["bug"]
  }'
```

Used by the frontend's trigger preview — "would this fire for X event?".

### Related endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/workflow-templates` | List all templates. |
| `GET /api/workflow-templates/{id}` | Get one template. |
| `POST /api/workflow-templates` | Create a template. |
| `PUT /api/workflow-templates/{id}` | Replace a template. |
| `DELETE /api/workflow-templates/{id}` | Delete a non-system template. |
| `POST /api/workflow-templates/match` | Legacy label-only matcher (kept for back-compat). |

---

## Examples

### Composable coding workflow (replaces the default pipeline)

```json
{
  "name": "agent-end-to-end",
  "description": "One agent does the whole task, then we run tests and open a PR.",
  "triggers": [{"type": "label", "match_any": ["feature", "bug"]}],
  "phases": [
    {
      "phase_name": "implement",
      "kind": "agent",
      "role": "coder",
      "params": {
        "prompt": "Task: {{run.title}}\n\nDescription:\n{{run.description}}\n\nContext:\n{{steps.init.context_summary}}",
        "mode": "task"
      },
      "timeout_seconds": 5400
    },
    {
      "phase_name": "test",
      "kind": "bash",
      "params": {"command": "make test"},
      "timeout_seconds": 1800,
      "failure_mode": "fail"
    },
    {
      "phase_name": "open_pr",
      "kind": "bash",
      "params": {
        "command": "gh pr create --title {{run.title}} --body 'Closes {{run.task_id}}'"
      },
      "trigger_mode": "wait_for_approval"
    }
  ]
}
```

### Scheduled monitoring workflow

```json
{
  "name": "hourly-error-summary",
  "triggers": [{"type": "schedule", "cron": "0 * * * *"}],
  "phases": [
    {
      "phase_name": "fetch",
      "kind": "bash",
      "params": {"command": "curl -s https://sentry.example.com/api/0/issues/?statsPeriod=1h"}
    },
    {
      "phase_name": "summarize",
      "kind": "agent",
      "role": "reviewer",
      "params": {
        "prompt": "Summarize these errors as a short Slack message:\n\n{{steps.fetch.stdout}}"
      }
    },
    {
      "phase_name": "post",
      "kind": "bash",
      "params": {
        "command": "curl -X POST $SLACK_WEBHOOK -d '{\"text\": \"{{steps.summarize.response}}\"}'"
      },
      "failure_mode": "skip"
    }
  ]
}
```

### PR-review workflow triggered by `review_requested`

```json
{
  "name": "auto-review",
  "triggers": [
    {"type": "pr_event", "source": "github", "action": "review_requested"}
  ],
  "phases": [
    {"phase_name": "pr_fetch", "kind": "legacy_phase"},
    {
      "phase_name": "review",
      "kind": "agent",
      "role": "reviewer",
      "params": {
        "prompt": "Review this PR diff:\n\n{{steps.pr_fetch.diff}}\n\nReport blocking issues."
      }
    },
    {
      "phase_name": "post_review",
      "kind": "bash",
      "params": {
        "command": "gh pr review {{run.task_id}} --comment --body '{{steps.review.response}}'"
      }
    }
  ]
}
```

---

## See Also

- [ADR-007 — Composable Step Workflows](../claudedocs/decisions/007-composable-step-workflows.md) — the design rationale.
- [`docs/WORKER_PIPELINE.md`](./WORKER_PIPELINE.md) — deprecated reference for the fixed 8-phase pipeline; preserved as the `default` template.
- [`docs/guides/09-webhook-setup.md`](./guides/09-webhook-setup.md) — wiring up GitHub, GitLab, Gitea, and Plane webhooks.
- `backend/worker/steps/` — implementation of `bash_step`, `agent_step`, and the templating engine.
- `backend/services/triggers/` — `TriggerMatcher` service.

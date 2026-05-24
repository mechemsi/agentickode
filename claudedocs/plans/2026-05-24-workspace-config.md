---
title: Workspace configuration — worker user, local-folder reuse, global workspace root
status: planned
date: 2026-05-24
related:
  - claudedocs/decisions/007-composable-step-workflows.md
---

## Goal

Make the platform usable from a developer's own machine (e.g. WSL) without
running everything as `root` and without re-cloning repos that are already
checked out locally. Three concrete settings:

1. **Configurable worker user** per workspace server (and override per project),
   replacing the silent `ssh.username == "root"` guard.
2. **Reuse-local-folder** for a project: if a path is set and points at an
   existing git repo, skip clone and operate on it in place (with worktree
   isolation per run).
3. **Global workspace root** in platform settings, used as the default for new
   servers and as the parent for the local platform server's workspaces.

## Why now

User context: running AutoDev against WSL host. Projects already cloned at
`~/projects/<name>`. Today the local platform server runs every coding
phase as `root` because `executor_for_server` returns a `LocalCommandService`
whose `username != "root"` in SSH terms, so the entire `worker_user` block
in `workspace_setup.py` is skipped. Every chat ends up as root, and every
run re-clones a repo the user already has.

## Scope (what changes)

### Backend

- **`WorkspaceServer`**: keep `worker_user` (already exists), but make the
  guard in `workspace_setup.py` check `server.server_type` (or
  `executor.kind`) instead of `ssh.username == "root"`. Local servers must
  honor `worker_user` too.
- **`ProjectConfig`**: new optional column `local_path` (`Text`, nullable).
  When set, workspace_setup short-circuits clone/fetch and uses this as
  `project_root`. Worktrees are still created beneath it (`.worktrees/...`)
  so the user's main checkout stays untouched.
- **`ProjectConfig`**: optional `worker_user_override` (`Text`, nullable) —
  used in place of `server.worker_user` when set.
- **New `PlatformSettings` row** (or extend existing settings table): a
  `default_workspace_root` field used as the seed value for new
  `WorkspaceServer.workspace_root` and for the platform server.
- **`workspace_setup` phase**: branch on `project.local_path`:
  - if set and `local_path` exists as a git repo → skip clone, set
    `task_run.workspace_path = project.local_path` (absolute), proceed to
    worktree creation.
  - else → existing flow.
- **Validation on project save**: if `local_path` is set, server-side
  validate that it exists, is a directory, and `<path>/.git` exists.

### Frontend

- **Settings page**: new "Workspace" section with `default_workspace_root`
  input.
- **Project form**: new "Local checkout path" field (optional). Help text:
  "If set, runs will operate on this folder instead of cloning. Must be a
  git repo on the selected workspace server."
- **Project form**: "Run as user" override (optional, falls back to the
  server's worker user).
- **Server form**: surface `worker_user` more prominently (it's already a
  field — make sure it's editable for `server_type=local` too).

### Migrations

- `038_workspace_config.py`:
  - `project_config.local_path TEXT NULL`
  - `project_config.worker_user_override TEXT NULL`
  - `platform_settings.default_workspace_root TEXT NOT NULL DEFAULT '/workspaces'`
    (or extend whatever settings storage already exists — TBD on read)
- Backfill is a no-op (all-nullable columns).

## Out of scope (this round)

- Sudoless run-as-user (assume `runuser`/`sudo` is available — same as today).
- Auto-detecting the current OS user as a default (operator picks).
- Sandboxing the worker user (cgroups, namespaces) — future hardening.
- Multi-tenant project ownership / permission model.

## Resolved design decisions (2026-05-24)

1. **Dirty-tree policy**: Refuse to start. Pre-flight check runs `git
   status --porcelain` in `local_path`; if non-empty, fail the run with
   a clear "commit or stash first" error before any side-effect.
2. **Local server worker user default**: Empty until explicitly set in the
   UI. Pre-existing behavior preserved (still `root` on the platform
   server) until operator opts in.
3. **Worker-user override scope**: Project + per-step. `ProjectConfig.worker_user_override`
   wins over server default; `step.params.run_as` (string) wins over the
   project override for that specific step. Matches the per-step pattern
   used by `trigger_mode` / `notify_source` in the composable step model.

## Success criteria

- [ ] A WSL user can configure the platform server's `worker_user` to their
      own account via the UI; runs no longer execute as `root`.
- [ ] A project pointed at `~/projects/myapp` skips the clone step; first
      run's `workspace_setup` completes in <2s instead of pulling.
- [ ] Global `default_workspace_root` seeds new server records and is shown
      in settings.
- [ ] Worktree isolation still works on a reused local folder — concurrent
      runs don't stomp on each other.
- [ ] Backend test coverage ≥80% for new branches in `workspace_setup`.
- [ ] Pre-existing `local_path is None` path is unchanged (regression-tested).

## Technical sketch

```
workspace_setup.run():
    server = resolve_server(task_run, services)
    worker_user = project.worker_user_override or server.worker_user
    is_local = server.server_type == "local"

    if project.local_path:
        validate_local_path(project.local_path, services)  # exists, is .git repo
        task_run.workspace_path = project.local_path
        # skip clone/fetch entirely
    else:
        # existing clone/fetch path
        ...

    if config.workspace_strategy == "worktree":
        worktree = make_worktree(task_run.workspace_path, task_run.id)
        task_run.workspace_path = worktree.path

    if worker_user and (is_local or ssh.username == "root"):
        chown(task_run.workspace_path, worker_user)
        # rest of safe.directory etc.
```

The `is_local or ssh.username == "root"` guard preserves today's SSH-remote
behavior and adds the local-server branch.

## Risks

- **Wrong-user file ownership**: if the operator points `local_path` at a
  folder owned by `domas` but sets `worker_user=coder`, `chown` will rewrite
  ownership of the user's working copy. Mitigation: validate that the
  configured `worker_user` already owns the target before chown'ing, or
  refuse to chown a `local_path` (only chown worktrees).
- **Stale lockfile / dirty working tree**: covered by open question #1.
- **Security**: `local_path` accepts any absolute path. Mitigation: validate
  it's under a configured allowlist (e.g. `default_workspace_root` or a
  per-server `allowed_local_paths`), and reject `..` traversal.

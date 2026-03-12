# ADR 006: Multi-Source Task Intake

## Status

Accepted

## Context

The AI Development Infrastructure originally supported only Plane as the task management source and Gitea as the git provider. Users need the ability to use GitHub Issues/Projects as an additional task source while keeping Plane support intact.

## Decision

Support multiple task sources (Plane, GitHub) and multiple git providers (Gitea, GitHub) simultaneously as orthogonal dimensions:

- **Task source** = where tasks originate (Plane webhooks, GitHub issue events)
- **Git provider** = where code is hosted (Gitea API, GitHub API)

These are independent: a Plane task can target a GitHub repo, and a GitHub Issue can target a Gitea repo.

### Key design choices

1. **Dispatch at the edges**: The core workflow (`AITaskWorkflow`) and most activities remain source-agnostic. Provider-specific logic lives only in:
   - Webhook entry points (n8n workflows)
   - `_inject_git_credentials()` — auth token format differs per provider
   - `push_branch_and_create_pr()` / `merge_pr()` — API endpoints differ
   - `update_task_source()` — notification routing

2. **Backward-compatible defaults**: All new fields default to existing behavior (`task_source="plane"`, `git_provider="gitea"`). Existing deployments require zero changes.

3. **`TaskContext` carries routing info**: The `task_source`, `git_provider`, and `task_source_meta` fields on `TaskContext` drive all dispatch decisions downstream.

4. **Database stores provider config per project**: The `project_configs` table has `task_source` and `git_provider` columns so each project can independently choose its task source and git provider.

## Consequences

### Positive

- Both Plane and GitHub can feed tasks simultaneously into the same deployment
- Adding a third task source (e.g., Linear, Jira) follows the same pattern
- No breaking changes to existing Plane+Gitea setups
- Clear separation: task management concerns vs. git hosting concerns

### Negative

- More conditional branches in activities (though isolated to specific functions)
- n8n requires a separate workflow for GitHub webhook ingestion (similar to the existing Plane workflow)
- `GITHUB_TOKEN` env var serves double duty (git operations + task source API) — may need separate tokens for fine-grained permissions in the future

## Related

- ADR 003: Workspace Types (workspace setup now handles both git providers)
- ADR 004: Node Separation (no architectural change — same nodes, same roles)

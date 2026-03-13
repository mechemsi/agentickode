# Architecture Decision Records

Key design decisions for the AgenticKode project. Each record explains the context, options considered, and rationale.

## Index

| ADR | Decision | Status |
|-----|----------|--------|
| [001](001-local-llm-first.md) | Local LLMs (Ollama) as the default backend | Accepted |
| [003](003-workspace-types.md) | Three workspace types (existing, new, cluster) | Accepted |
| [005](005-multi-agent-pipeline.md) | Multi-agent pipeline (Planner/Coder/Reviewer) | Accepted |
| [006](006-multi-source-task-intake.md) | Multi-source task intake (Plane, GitHub, Gitea, GitLab) | Accepted |

## ADR Template

When adding a new decision record, use this format:

```markdown
# ADR-NNN: Title

## Status
Accepted | Superseded by ADR-NNN | Deprecated

## Context
What is the issue that we're seeing that motivates this decision?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or more difficult as a result of this decision?
```

---
name: plan
description: Quick feature planning that writes implementation plans to docs/plans/. Use when the user runs /plan or asks to plan a feature, endpoint, integration, or architectural change.
---

# Plan Skill

When the user runs /plan:

1. Ask for the feature name if not provided
2. Read CLAUDE.md to understand current architecture and conventions
3. Explore relevant existing code to understand patterns in use
4. Immediately create `docs/plans/<feature-name>.md`
5. Write the plan directly to the file — do NOT enter plan mode or ask for approval

## Plan Structure

```markdown
# <Feature Name>

## Summary
One paragraph describing the feature and its purpose.

## Files to Create/Modify
| File | Action | Purpose |
|------|--------|---------|
| backend/api/... | create/modify | ... |
| backend/services/... | create/modify | ... |
| tests/unit/... | create | ... |
| frontend/src/... | create/modify | ... |

## Implementation Phases

### Phase 1: <name>
- [ ] Task with specific file and function references
- [ ] Task ...

### Phase 2: <name>
- [ ] Task ...

## Architecture Notes
- Which Protocols to implement/use (GitProvider, RoleAdapter, etc.)
- ServiceContainer integration points
- Database model changes requiring Alembic migrations

## Testing Strategy
- Unit tests for each new module
- Integration tests for cross-module flows
- Docker commands to run: `make test-file F=tests/unit/test_<module>.py`
```

## Project Conventions to Follow

- All new Python files need AGPLv3 license header
- All new TypeScript files need AGPLv3 license header
- Max 200 lines per file — split if larger
- Use existing Protocols (GitProvider, RoleAdapter) — never call APIs directly
- Use ServiceContainer for DI — never import services directly in phases
- Use Repository pattern for DB access — no inline SQLAlchemy in routes
- All commands run in Docker: `docker compose -f docker-compose.dev.yml exec ...`

## Constraints

- Keep exploration to under 2 minutes
- Bias toward action — write the plan, don't deliberate
- Output: "Plan written to docs/plans/<feature-name>.md"

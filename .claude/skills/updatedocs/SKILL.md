---
name: updatedocs
description: Analyze codebase changes and update CLAUDE.md and README.md to reflect current state. Use after major refactoring, structural changes, or when documentation may be stale. Triggers on /updatedocs.
---

# Documentation Updater

Analyze codebase state and update project documentation.

## Scope

Arguments: `all` (default), `claude`, `readme`, or a path to a changed area.

## Step 1: Analyze Current State

```
1. Run `git diff main --stat` (or `git diff HEAD~10 --stat` if on main) to see recent changes
2. Run `git log --oneline -20` to understand recent commit history
3. Read the current CLAUDE.md and README.md
4. Scan key directories for structural changes:
   - backend/api/, backend/services/, backend/worker/phases/
   - frontend/src/pages/, frontend/src/components/
   - alembic/versions/
   - .github/workflows/
   - docs/
```

## Step 2: Identify Documentation Gaps

Compare gathered state against existing docs. Look for:

- **New components** not mentioned in docs
- **Removed components** still referenced in docs
- **Changed architecture** (new services, moved responsibilities)
- **New or changed commands** (build, deploy, test)
- **Changed environment variables** or configuration
- **New conventions** established by recent code

## Step 3: Update CLAUDE.md

Focus on: architecture accuracy, code structure, command reference, conventions, project status.

**Rules:**
- Concise and scannable — tables over paragraphs
- No generic advice — only project-specific guidance
- Don't duplicate what reading a single file reveals
- Focus on cross-cutting concerns

## Step 4: Update README.md

Focus on: architecture diagrams, component tables, quick start, directory structure.

## Step 5: Verify Consistency

- CLAUDE.md and README.md don't contradict each other
- Referenced files/scripts actually exist
- Ports and env vars are consistent

## Step 6: Report Changes

```
## Documentation Updates
### CLAUDE.md
- [what changed and why]
### README.md
- [what changed and why]
### No Changes Needed
- [sections verified as accurate]
```

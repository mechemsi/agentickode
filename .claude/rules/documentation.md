# Documentation Rules

All project documentation lives in `claudedocs/`. Claude maintains these docs as part of the development workflow.

## When to Create Docs

| Folder | When | Who creates it |
|--------|------|----------------|
| `plans/` | Before starting a new feature or significant change | Developer or Claude during planning |
| `implementations/` | After a feature is shipped and working | Claude after completing implementation |
| `decisions/` | When choosing between multiple technical approaches | Developer or Claude when a decision is made |
| `runbooks/` | When a manual process is repeated more than once | Anyone who discovers the process |

## File Naming

- **Plans**: `YYYY-MM-DD-short-name.md` (e.g., `2026-03-28-auth-system.md`)
- **Implementations**: `YYYY-MM-DD-short-name.md` (e.g., `2026-03-28-project-setup.md`)
- **Decisions**: `NNN-short-name.md` with sequential numbering (e.g., `001-app-router.md`)
- **Runbooks**: `short-name.md` (e.g., `database-migration.md`)

## Required Frontmatter

Every doc must start with YAML frontmatter:

```yaml
---
title: Human-readable title
status: planned | in-progress | implemented | abandoned | accepted
date: YYYY-MM-DD
related: [optional list of related doc paths]
---
```

Runbooks only need `title`.

## INDEX.md

`claudedocs/INDEX.md` is the master index. It must be updated whenever a doc is added, removed, or changes status.

Claude should read INDEX.md first when looking for project context, before scanning individual files.

## Plan Docs

A plan doc must include:
- **Goal**: One sentence on what this achieves
- **Scope**: In scope and out of scope
- **Technical Approach**: How it will be built
- **Success Criteria**: Checkboxes that define "done"

## Implementation Docs

An implementation doc must include:
- **What Was Built**: Summary of the feature
- **Key Files**: Table of important files and their purpose
- **How It Works**: Brief architecture or data flow description
- **Notes**: Gotchas, limitations, or future work

## Decision Docs (ADRs)

Follow the Architecture Decision Record format:
- **Context**: Why this decision was needed
- **Options Considered**: At least 2 options with pros/cons
- **Decision**: What was chosen
- **Rationale**: Why this option won
- **Consequences**: What changes as a result

## Runbook Docs

A runbook must include:
- **When to Use**: What triggers this process
- **Steps**: Numbered, copy-pasteable commands (using Docker)
- **Common Issues**: Table of problems and fixes

## Rules

- Keep docs concise — prefer tables and bullet points over paragraphs
- Link between related docs using relative paths
- Update `status` in frontmatter when a plan moves to implementation or is abandoned
- Never delete docs — change status to `abandoned` with a note explaining why
- Do not duplicate information that belongs in code comments or README

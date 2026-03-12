---
name: updatedocs
description: Analyze codebase changes and update CLAUDE.md and README.md to reflect current state
argument-hint: "[scope: 'all' | 'claude' | 'readme' | path to changed area]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Task
---

<objective>
Analyze the current state of the codebase and update project documentation (CLAUDE.md and README.md) to accurately reflect the architecture, commands, conventions, and structure.

This skill should be invoked:
1. On demand via `/updatedocs`
2. Automatically after completing a major planning or refactoring phase
3. When significant structural changes have been made (new services, changed architecture, new workflows)

Output: Updated CLAUDE.md and/or README.md with accurate, current information.
</objective>

<context>
Scope: $ARGUMENTS
- "all" or empty: Update both CLAUDE.md and README.md
- "claude": Update only CLAUDE.md
- "readme": Update only README.md
- path: Focus analysis on a specific changed area and update docs accordingly
</context>

<instructions>

## Step 1: Analyze Current State

Gather information about what has changed:

```
1. Run `git diff main --stat` (or `git diff HEAD~10 --stat` if on main) to see recent changes
2. Run `git log --oneline -20` to understand recent commit history
3. Read the current CLAUDE.md and README.md
4. Scan key directories for structural changes:
   - workflows/ (new workflows, changed agents)
   - docker/ (new services, changed compose files)
   - infrastructure/ (new nodes, changed configs)
   - config/ (new service configs)
   - scripts/ (new deployment scripts)
   - docs/ (new documentation)
```

## Step 2: Identify Documentation Gaps

Compare gathered state against existing docs. Look for:

- **New components** not mentioned in docs
- **Removed components** still referenced in docs
- **Changed architecture** (new services, moved responsibilities, new network topology)
- **New or changed commands** (build, deploy, test commands)
- **Changed environment variables** or configuration
- **New conventions** established by recent code
- **Updated dependencies** or technology choices
- **Phase/status changes** per PLAN.md

## Step 3: Update CLAUDE.md

CLAUDE.md is for Claude Code agents. Focus on:

- Architecture accuracy (nodes, services, IPs, ports)
- Workflow code structure (new files, changed interfaces, new dataclasses)
- Command reference (any new scripts or changed invocations)
- Service endpoints and environment variables
- Conventions and rules
- Project status (current phase)

**Rules for CLAUDE.md:**
- Keep it concise and scannable — tables over paragraphs
- No generic development advice — only project-specific guidance
- Don't duplicate what can be discovered by reading a single file
- Focus on cross-cutting concerns that require reading multiple files to understand
- Update the project status section to match PLAN.md

## Step 4: Update README.md

README.md is for humans. Focus on:

- Architecture diagram accuracy
- Component table (any new tools, changed purposes)
- Quick start / deployment instructions
- Directory structure (new directories)
- Model assignments (if changed)
- Operational model changes

**Rules for README.md:**
- Keep the ASCII architecture diagram accurate
- Ensure the component table is complete
- Update directory structure listing if new top-level dirs exist
- Keep Quick Start working — verify referenced scripts exist

## Step 5: Verify Consistency

After updates, verify:
- CLAUDE.md and README.md don't contradict each other
- Referenced files/scripts actually exist
- IP addresses and ports are consistent across both files
- Environment variable names match actual code usage

## Step 6: Report Changes

Summarize what was updated and why. Format:

```
## Documentation Updates

### CLAUDE.md
- [what changed and why]

### README.md
- [what changed and why]

### No Changes Needed
- [sections verified as accurate]
```

</instructions>

<quality-gates>
- All referenced files and scripts must exist in the repo
- Architecture descriptions must match actual docker-compose and infrastructure files
- Environment variable names must match what code actually reads
- No speculative content — only document what exists
- Both files must be internally consistent and consistent with each other
</quality-gates>

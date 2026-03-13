---
name: dev-flow
description: Full development workflow orchestration — requirements analysis, architecture planning, implementation, code review, and testing using specialized sub-agents with approval gates. Use when the user wants to develop a complete feature end-to-end, or asks for the full development flow. Triggers on /dev-flow.
---

# Development Flow Orchestrator

Multi-agent workflow with approval gates for end-to-end feature development.

## Workflow

```
req-analyzer → arch-planner → [user approval] → implementer → reviewer → [pass/fail] → tester
```

## Execution Steps

### 1. Requirements Analysis (dispatch sub-agent, model: sonnet)

Prompt the sub-agent with the `references/req-analyzer.md` prompt.

### 2. Architecture Planning (dispatch sub-agent, model: opus)

Prompt the sub-agent with the `references/arch-planner.md` prompt.

### 3. User Approval Gate

Ask the user to review the architecture plan:
- **Approve** → proceed to implementation
- **Revise** → dispatch plan-reviser sub-agent with `references/plan-reviser.md` prompt, then return to approval
- **Cancel** → stop workflow

### 4. Implementation (dispatch sub-agent, model: sonnet)

Prompt the sub-agent with the `references/implementer.md` prompt.

### 5. Code Review (dispatch sub-agent, model: opus)

Prompt the sub-agent with the `references/reviewer.md` prompt.

If the review verdict is **FAIL**, stop and report issues to user.
If **PASS**, proceed to testing.

### 6. Testing (dispatch sub-agent, model: sonnet)

Prompt the sub-agent with the `references/tester.md` prompt.

## Sub-Agent Prompts

All sub-agent prompts are stored in the `references/` directory. Read the appropriate file when dispatching each agent.

# ADR-005: Multi-Agent Pipeline (Planner / Coder / Reviewer)

## Status

Accepted

## Context

When an AI task arrives, someone (or something) must decompose it into work, implement the changes, and verify the result. The two main approaches are:

1. **Single agent**: One LLM does everything — reads the task, plans, writes code, reviews its own work
2. **Multi-agent pipeline**: Specialized agents with different models handle distinct phases

Single-agent is simpler but has known failure modes:
- LLMs are poor at self-review (they tend to approve their own work)
- One model can't be optimal for both reasoning (planning) and code generation
- Errors compound without an independent check

## Decision

**Use a three-agent pipeline: Planner → Coder → Reviewer, each running a different model optimized for its role.**

| Agent | Model | Why This Model |
|-------|-------|----------------|
| **Planner** | Qwen2.5-Coder-32B | Largest model for strongest reasoning. Needs to understand task requirements and decompose into actionable subtasks. |
| **Coder** | Devstral-24B | Code-specialized model from Mistral. Trained specifically for code generation tasks. |
| **Reviewer** | Qwen2.5-Coder-14B | Smaller model is sufficient for evaluation (judging is easier than generating). Runs on the secondary GPU. |

The agents are coordinated by LangGraph as a directed graph with conditional edges:

```
Planner → Coder → Reviewer
                     ↓
              Issues found?
             ↙            ↘
           Yes              No
            ↓                ↓
        Fix Agent        Create PR
            ↓
        Reviewer (again, max 3 loops)
```

## Consequences

**Benefits:**
- **Independent review**: Reviewer catches errors that the Coder's own model would overlook
- **Model optimization**: Each role uses the best-fit model for its task type
- **GPU utilization**: Planner/Coder share the large GPU (sequential), Reviewer uses the smaller GPU (can run in parallel)
- **Clear failure attribution**: When a task fails, you can see which phase failed and why
- **Retry granularity**: Only the failed phase retries, not the entire pipeline

**Trade-offs:**
- More complex than a single-agent approach
- Inter-agent communication requires structured state (LangGraph's `AgentState`)
- The review-fix loop can waste time on minor style issues if the reviewer is overly critical
- Three different models to maintain and keep in VRAM

**Mitigations:**
- LangGraph provides clean abstractions for agent coordination
- The `AgentState` TypedDict makes state passing explicit and debuggable
- Review-fix loop is capped at 3 iterations, then escalates to human
- Models swap in/out of VRAM automatically via Ollama (5-minute idle timeout)

**Why not more agents?**

We considered adding a dedicated Test Agent and a Documentation Agent. For now, testing is handled within the Coder phase (run tests after changes) and documentation is not auto-generated. This keeps the pipeline lean. More agents can be added later if needed — LangGraph's graph structure makes it straightforward to insert new nodes.

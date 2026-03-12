# ADR-001: Local LLMs as the Default Backend

## Status

Accepted

## Context

The system needs LLM inference for planning, coding, and reviewing tasks. The two main approaches are:

1. **Cloud APIs** (Claude, OpenAI, etc.) — high quality, zero hardware investment, but ongoing cost per token and data leaves the network
2. **Local inference** (Ollama with consumer GPUs) — requires hardware investment, lower quality ceiling, but no per-token cost and full data privacy

Our primary use case is autonomous handling of routine development tasks (bug fixes, small features, dependency updates). These tasks are high-volume but individually low-stakes — a good fit for capable-but-not-frontier models.

## Decision

**Default to local LLMs via Ollama. Cloud APIs are opt-in per task (via `use-claude` label).**

Specifically:
- All automated workflows use Ollama on ai-gpu-01 by default
- Tasks labeled `use-claude` in Plane switch all agents to Claude API
- The system is designed so swapping backends requires no workflow changes — only the LLM client configuration changes

## Consequences

**Benefits:**
- Zero marginal cost per task — encourages liberal use of AI assistance
- Full data privacy — code never leaves the internal network by default
- No vendor dependency — the system works without internet access
- Predictable performance — no API rate limits or outages from external providers

**Trade-offs:**
- Requires GPU hardware investment (RTX 3090 + RTX 5060 Ti in reference setup)
- Local model quality is below frontier cloud models for complex reasoning
- GPU VRAM limits model size and concurrency
- Maintenance burden for GPU drivers, model updates, and hardware

**Mitigations:**
- The `use-claude` escape hatch allows cloud quality when needed
- Model improvements (Qwen, Devstral) have steadily narrowed the quality gap
- VRAM constraints are manageable with model swapping and quantization

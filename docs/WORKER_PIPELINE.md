# Worker Pipeline (Legacy Reference)

> **This document is deprecated.** See [workflows.md](workflows.md) for the current composable-workflow model. Kept for reference; the architecture documented here (fixed 8-phase pipeline) is preserved as the `default` workflow template for back-compat.

The 8-phase pipeline (`workspace_setup → init → planning → coding → testing → reviewing → approval → finalization`) used to be the only execution model. It is now one of several workflow templates — the `default` seeded template composes every step with `kind: legacy_phase`, and the underlying phase modules in `backend/worker/phases/` are unchanged.

- For the rationale behind the rewrite, see [ADR-007 — Composable Step Workflows](../claudedocs/decisions/007-composable-step-workflows.md).
- For migrating a custom template to the new `bash` / `agent` step kinds, see the [Migration table in workflows.md](workflows.md#migrating-from-the-legacy-pipeline).
- For the full step kind / trigger / templating reference, see [workflows.md](workflows.md).

The previous 1500-line reference (engine polling, per-phase prompt templates, SSH command snippets, timeout tables) is retained in git history if you need it — `git log --follow docs/WORKER_PIPELINE.md`.

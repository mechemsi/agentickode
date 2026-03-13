---
name: check
description: Run targeted or full CI checks in Docker. Use when verifying code changes, before commits, or when the user wants to lint/test/typecheck. Triggers on /check or when user asks to run tests, lint, or validate code.
---

# CI Check Runner

Run CI checks based on the scope argument.

## Scope Behavior

**`/check` or `/check all`** — Full CI (mirrors GitHub Actions):
```bash
make ci
```

**`/check backend`** — Backend only:
```bash
make ci-backend
```

**`/check frontend`** — Frontend only:
```bash
make ci-frontend
```

**`/check quick`** — Lint + format only (fast):
```bash
make lint-fix && make fmt && make flint-fix
```

**`/check <file-path>`** — Targeted check on specific file(s):

For Python files:
```bash
docker compose -f docker-compose.dev.yml exec backend ruff check <file> --fix
docker compose -f docker-compose.dev.yml exec backend ruff format <file>
docker compose -f docker-compose.dev.yml exec backend pyright <file>
```
Then find and run the corresponding test file (e.g., `backend/api/runs.py` → `tests/unit/test_runs.py`).

For TypeScript files:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx eslint <file> --fix
```
Then find and run the corresponding test file (e.g., `src/pages/Dashboard.tsx` → `src/__tests__/Dashboard.test.tsx`).

## Rules

- ALL commands run in Docker — never on host
- Report results concisely: pass/fail per check
- On failure, show the relevant error output
- Do not fix issues automatically — just report them

---
name: scaffold
description: Scaffold new backend endpoints, services, worker phases, or frontend pages with proper structure, license headers, and tests. Use when creating new API routes, services, pipeline phases, or React pages. Triggers on /scaffold.
---

# Module Scaffolder

Generate boilerplate files for new AgenticKode modules with all project conventions pre-applied.

## Usage

```
/scaffold endpoint <name>     # New API route + schema + test
/scaffold service <name>      # New service class + test
/scaffold phase <name>        # New worker pipeline phase + test
/scaffold page <name>         # New React page + test
```

## Step 1: Parse Arguments

Extract `<type>` and `<name>` from the arguments. If missing, ask the user.

## Step 2: Read Existing Examples

Before generating, read one existing file of the same type to match the exact patterns:
- endpoint: Read `backend/api/runs.py` for route patterns
- service: Read `backend/services/ollama_service.py` for service patterns
- phase: Read `backend/worker/phases/coding.py` for phase patterns
- page: Read `frontend/src/pages/Dashboard.tsx` for page patterns

## Step 3: Generate Files

### endpoint `<name>`
1. `backend/api/<name>.py` — FastAPI router with CRUD operations, Depends() for session/services
2. `backend/schemas.py` — Add Pydantic schemas (or create `backend/schemas/<name>.py` if schemas.py > 180 lines)
3. `tests/unit/test_<name>.py` — pytest tests using `client` fixture and mocked services
4. Update `backend/main.py` to include the new router

### service `<name>`
1. `backend/services/<name>.py` — Service class with constructor-injected httpx client
2. `tests/unit/test_<name>_service.py` — pytest tests with mocked HTTP client
3. Update `backend/services/container.py` to add to ServiceContainer

### phase `<name>`
1. `backend/worker/phases/<name>.py` — Phase function: `async def run(task_run, session, services) -> None | str`
2. `tests/unit/test_<name>_phase.py` — pytest tests with mock_services fixture
3. Update `backend/worker/phases/registry.py` to register the phase

### page `<name>`
1. `frontend/src/pages/<Name>.tsx` — React page component with Tailwind styling
2. `frontend/src/__tests__/<Name>.test.tsx` — Vitest test with React Testing Library
3. Update `frontend/src/App.tsx` to add the route

## Mandatory on ALL Generated Files

**Python files** — first 3 lines:
```python
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com
```

**TypeScript files** — first 3 lines:
```typescript
// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com
```

## Step 4: Verify

Run targeted lint/typecheck on generated files:
```bash
# Python
docker compose -f docker-compose.dev.yml exec backend ruff check backend/<file>.py --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/<file>.py

# TypeScript
docker compose -f docker-compose.dev.yml exec frontend npx eslint src/<file>.tsx --fix
```

## Rules

- Every file must be under 200 lines
- Match the exact import style and patterns of existing code
- Never generate placeholder/TODO code — all functions must work
- Always create the corresponding test file

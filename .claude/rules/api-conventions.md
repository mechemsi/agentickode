# API Design Conventions

All API routes follow these conventions consistently.

## Route Structure
```
/api/[resource]              GET (list), POST (create)
/api/[resource]/{id}         GET (single), PUT (replace), PATCH (update), DELETE
```

## Framework
- **FastAPI** with async route handlers
- **Pydantic** schemas for request/response validation
- **SQLAlchemy** async sessions for database access
- **Repository pattern** for all DB queries

## Response Format
FastAPI returns Pydantic models directly. List endpoints return arrays.

## HTTP Status Codes
| Situation             | Code |
|----------------------|------|
| Success (GET/PATCH)  | 200  |
| Created (POST)       | 201  |
| No content (DELETE)  | 204  |
| Bad request          | 400  |
| Unauthorized         | 401  |
| Forbidden            | 403  |
| Not found            | 404  |
| Conflict             | 409  |
| Validation error     | 422  |
| Server error         | 500  |

## Validation
- Use Pydantic schemas for all request body validation
- FastAPI handles validation automatically via type annotations
- Return 422 with field-level errors for validation failures

## Route Handler Pattern
```python
@router.post("/runs", status_code=201)
async def create_run(
    payload: CreateRunRequest,
    session: AsyncSession = Depends(get_session),
) -> TaskRunResponse:
    repo = TaskRunRepository(session)
    run = await repo.create(payload)
    return TaskRunResponse.model_validate(run)
```

## Architecture Rules
1. **Repository Pattern**: Use `TaskRunRepository`, `ProjectConfigRepository` for DB access. No inline SQLAlchemy in handlers.
2. **Dependency Injection**: Use FastAPI `Depends()` for session, services, auth.
3. **Shared HTTP Client**: Use `get_http_client()` — never create standalone httpx clients.
4. **GitProvider Protocol**: Use `get_git_provider()` factory — never call git APIs directly.
5. **RoleAdapter Protocol**: Use `RoleResolver` — never call agent APIs directly.

## WebSocket Endpoints
- `/ws/logs/{run_id}` — real-time log streaming
- `/ws/terminal/{session_id}` — SSH terminal bridge
- `/ws/events` — dashboard event stream

## SSE Endpoints
- `/api/runs/{run_id}/stream` — run status streaming

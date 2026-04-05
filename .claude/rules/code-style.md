# Code Style Rules

These rules are automatically applied by Claude on every task.

## Python (Backend)

### Formatting
- **ruff** handles formatting and linting — no style debates
- 4-space indentation
- Double quotes for strings
- Max line length: 100 characters
- Always use type hints for function signatures

### Naming Conventions
| Thing           | Convention        | Example                      |
|----------------|-------------------|------------------------------|
| Variables       | snake_case        | `user_data`, `is_loading`    |
| Functions       | snake_case        | `get_user_by_id()`, `format_date()` |
| Classes         | PascalCase        | `TaskRun`, `GitProvider`     |
| Constants       | SCREAMING_SNAKE   | `MAX_RETRIES`, `API_BASE_URL`|
| Files           | snake_case        | `task_run.py`, `git_ops.py`  |
| Protocols       | PascalCase        | `GitProvider`, `RoleAdapter` |

### Design Principles
- Accept Protocols, return concrete types
- Keep Protocols small (1-3 methods)
- Use `async/await` for all I/O operations
- Prefer Pydantic models for data validation

### Error Handling
Always wrap errors with context:
```python
try:
    result = await service.execute(task)
except ServiceError as e:
    raise PhaseError(f"Failed to execute task {task.id}: {e}") from e
```

### Imports
- Group imports: 1) stdlib 2) third-party 3) local
- Use absolute imports from `backend.` package
- Never use wildcard imports

## TypeScript (Frontend)

### Formatting
- 2-space indentation
- Single quotes for strings
- Trailing commas in multi-line objects/arrays
- Always use semicolons

### Naming Conventions
| Thing           | Convention        | Example                      |
|----------------|-------------------|------------------------------|
| Variables       | camelCase         | `userData`, `isLoading`      |
| Functions       | camelCase         | `getUserById()`, `formatDate()` |
| Components      | PascalCase        | `RunDetail`, `PhaseTimeline` |
| Constants       | SCREAMING_SNAKE   | `MAX_RETRIES`, `API_BASE_URL`|
| Files (component)| PascalCase       | `RunDetail.tsx`              |
| Files (util)    | camelCase         | `apiClient.ts`               |
| Types/Interfaces| PascalCase        | `TaskRun`, `ApiResponse`     |

### Components
- One component per file
- Props interface defined at the top of the file
- Destructure props in the function signature
- Keep components under 150 lines — extract sub-components if larger

### Error Handling
- All async functions must have try/catch or error boundaries
- Never swallow errors silently — always log or display
- User-facing errors must be friendly messages

## Shared Rules
- Max 200 lines per file. Split if larger.
- No large singletons. Use dependency injection.
- Functions should do one thing well
- Pure functions preferred — avoid side effects where possible

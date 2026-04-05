# Testing Rules

All new features and bug fixes must include tests.

## Test Frameworks
- **Backend unit tests**: pytest (`tests/unit/`)
- **Backend integration tests**: pytest + SQLite (`tests/integration/`)
- **Frontend unit tests**: Vitest + React Testing Library (`frontend/src/__tests__/`)

## All Commands Run in Docker
```bash
# Backend
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -v
docker compose -f docker-compose.dev.yml exec backend pytest tests/ --cov=backend --cov-report=term-missing

# Frontend
docker compose -f docker-compose.dev.yml exec frontend npm test
docker compose -f docker-compose.dev.yml exec frontend npm run test:coverage
```

## What to Test
- Every new service function → unit test
- Every API route → integration test
- Every bug fix → regression test that would have caught it
- Every new React component → component test

## Backend Test Structure
```python
class TestMyService:
    async def test_returns_expected_for_valid_input(self, db_session):
        result = await my_service.execute(valid_input)
        assert result.status == "success"

    async def test_raises_for_invalid_input(self, db_session):
        with pytest.raises(ValidationError):
            await my_service.execute(invalid_input)
```

## Backend Test Conventions
- Use `mock_services` fixture for mocked `ServiceContainer`
- Use `make_task_run` factory fixture for creating test `TaskRun` records
- Tests use in-memory SQLite with JSONB→JSON mapping (see `conftest.py`)
- Mock external services (SSH, HTTP clients) — never call them in tests
- Use `AsyncMock` for async service methods

## Frontend Test Structure
```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

describe('MyComponent', () => {
  it('renders expected content', () => {
    render(<MemoryRouter><MyComponent /></MemoryRouter>);
    expect(screen.getByText('Expected')).toBeInTheDocument();
  });
});
```

## Frontend Test Conventions
- Mock API calls with `vi.mock("../api", ...)`
- Wrap routed components in `<MemoryRouter>`
- Use `data-testid` attributes for selectors, not CSS classes

## Naming Conventions
- Backend: `test_<module>.py` (e.g., `test_pipeline.py`)
- Frontend: `<Component>.test.tsx` (e.g., `RunDetail.test.tsx`)
- Test names: plain English describing behavior
  - `test_returns_null_when_user_not_found`
  - `'renders error message when API fails'`

## Coverage Goals
- Backend services: 80%+
- API routes: 70%+
- Frontend components: 70%+
- Overall: maintain 70%+
- Don't chase coverage numbers — test behavior, not lines

## License Headers
All test files must include the license header (see CLAUDE.md).

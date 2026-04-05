# /deploy — Deployment Checklist

Walk through all pre-deploy steps and prepare the branch for deployment.

## Pre-deploy Checklist
1. **Lint** — run `docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/`, fix all errors
2. **Format** — run `docker compose -f docker-compose.dev.yml exec backend ruff format backend/ tests/`
3. **Type check** — run `docker compose -f docker-compose.dev.yml exec backend pyright backend/`, fix all errors
4. **Backend tests** — run `docker compose -f docker-compose.dev.yml exec backend pytest tests/ -v`, ensure all pass
5. **Frontend lint** — run `docker compose -f docker-compose.dev.yml exec frontend npm run lint`
6. **Frontend tests** — run `docker compose -f docker-compose.dev.yml exec frontend npm test`
7. **Migrations** — check if any Alembic migrations are pending (`docker compose -f docker-compose.dev.yml exec backend alembic history`)
8. **License headers** — verify all new files have license headers
9. **Env vars** — list any new env vars added; remind to set them in production
10. **Breaking changes** — flag any API changes that require coordination
11. **PR description** — draft a clear PR description with:
    - What changed and why
    - How to test
    - Any risks or rollback notes

## Post-deploy Notes
- Monitor container logs for errors after deploy
- Confirm key API endpoints respond correctly
- Verify WebSocket connections work

## Usage
```
/deploy
/deploy --branch feat/new-feature
```

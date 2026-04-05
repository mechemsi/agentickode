# Skill: Deploy Workflow

**Type**: Auto-invoked workflow
**Triggers**: When asked to deploy, prepare a release, or run pre-deploy checks

## Purpose
Execute a structured, safe deployment checklist to ensure nothing is missed before shipping.

## Workflow

### Phase 1 — Code Quality Gates
```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/
docker compose -f docker-compose.dev.yml exec backend ruff format --check backend/ tests/
docker compose -f docker-compose.dev.yml exec backend pyright backend/
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -v
docker compose -f docker-compose.dev.yml exec frontend npm run lint
docker compose -f docker-compose.dev.yml exec frontend npm test
```
Stop and report if any phase fails. Do not proceed to Phase 2.

### Phase 2 — Database
```bash
docker compose -f docker-compose.dev.yml exec backend alembic history
docker compose -f docker-compose.dev.yml exec backend alembic heads
```
- If migrations are pending: list them and confirm with the developer before applying
- If models changed but no migration exists: warn loudly
- Never run `alembic upgrade head` without explicit developer confirmation

### Phase 3 — License Headers
- Verify all new/modified `.py` files have the AGPLv3 license header
- Verify all new/modified `.ts`/`.tsx` files have the AGPLv3 license header
- Flag any missing headers

### Phase 4 — Environment Variables Audit
- Check `backend/config.py` for any new Settings fields
- List any new env vars the developer must set in production
- Flag any vars that changed format or meaning

### Phase 5 — Breaking Changes Check
- Review API changes: any removed/renamed endpoints or changed response shapes?
- Review DB changes: any dropped columns or tables?
- Review webhook payload changes that could break integrations
- Flag anything requiring coordinated rollout

### Phase 6 — PR / Release Notes
Draft a release summary:
```
## What Changed
[bullet list of features/fixes]

## How to Test
[steps to verify key flows]

## Database Changes
[list of migrations, or "None"]

## New Environment Variables
[list, or "None"]

## Risk Level
[ ] Low — bug fix, no schema change
[ ] Medium — new feature, additive changes only
[ ] High — breaking change, schema migration
```

### Phase 7 — Final Sign-off
- Summarize pass/fail for each phase
- Remind developer to monitor logs post-deploy
- Update `docs/IMPLEMENTATION_LOG.md` with release entry

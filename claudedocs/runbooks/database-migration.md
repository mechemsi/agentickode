---
title: Database Migration
---

# Database Migration

## When to Use
When adding, modifying, or removing database columns/tables, or when applying pending migrations.

## Steps

### 1. Create a new migration
```bash
docker compose -f docker-compose.dev.yml exec backend alembic revision --autogenerate -m "description of change"
```

### 2. Review the generated migration
Check `alembic/versions/<hash>_description.py` for correctness. Verify:
- Correct `upgrade()` and `downgrade()` functions
- No unintended changes (autogenerate can miss or over-detect)

### 3. Apply the migration
```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

### 4. Verify
```bash
docker compose -f docker-compose.dev.yml exec backend alembic current
docker compose -f docker-compose.dev.yml exec backend alembic history
```

### 5. Run tests
```bash
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -v
```

## Common Issues

| Problem | Fix |
|---------|-----|
| "Target database is not up to date" | Run `alembic upgrade head` first |
| Autogenerate misses a change | Write the migration manually |
| Migration conflicts (multiple heads) | Run `alembic merge heads -m "merge"` |
| Need to rollback | `alembic downgrade -1` (one step back) |

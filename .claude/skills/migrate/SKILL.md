---
name: migrate
description: Database migration helper — create, apply, or check Alembic migrations in Docker. Use when the user needs to create a new migration, apply pending migrations, check migration status, or roll back. Triggers on /migrate.
---

# Alembic Migration Manager

Manage database migrations inside Docker.

## Actions

**`/migrate new <message>`** — Create a new migration:
1. Check for multiple heads first (fork detection):
   ```bash
   docker compose -f docker-compose.dev.yml exec backend alembic heads
   ```
2. If multiple heads exist, warn the user and suggest merging
3. Generate the migration:
   ```bash
   docker compose -f docker-compose.dev.yml exec backend alembic revision --autogenerate -m "<message>"
   ```
4. Read the generated migration file and review it for correctness
5. Report what tables/columns were detected

**`/migrate apply`** — Apply pending migrations:
```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

**`/migrate status`** — Show current migration state:
```bash
docker compose -f docker-compose.dev.yml exec backend alembic current
docker compose -f docker-compose.dev.yml exec backend alembic heads
```

**`/migrate history`** — Show migration history:
```bash
docker compose -f docker-compose.dev.yml exec backend alembic history --verbose -r -5:
```

**`/migrate downgrade`** — Roll back the last migration:
```bash
docker compose -f docker-compose.dev.yml exec backend alembic downgrade -1
```

## Rules

- ALL commands run in Docker
- Always check for fork (multiple heads) before creating new migrations
- Review auto-generated migrations — they often miss constraints or get column types wrong
- Migration files are in `alembic/versions/`

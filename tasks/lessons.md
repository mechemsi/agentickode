
## 2026-03-25 — Didn't use skill-creator skill when creating skills
**What went wrong:** Created 6 autodev skills manually without invoking the `skill-creator:skill-creator` or `superpowers:writing-skills` skill first, which could have ensured better structure, triggering accuracy, and best practices.
**Rule for next time:** When creating or editing skills, always invoke the `superpowers:writing-skills` skill before writing any SKILL.md files.

## 2026-03-25 — Project IDs with slashes break non-:path routes
**What went wrong:** The workspace-readiness endpoint used `{project_id}` without `:path`, but project IDs can contain slashes (e.g., `viminkas/prestashop`). FastAPI rejected the encoded `%2F` as a 404.
**Rule for next time:** Always use `{project_id:path}` for project ID route parameters, since project IDs can contain slashes. Check existing routes for the pattern before adding new ones.

## 2026-06-05 — Alembic migration collided with the runtime auto-migrate (backend crash-loop)
**What went wrong:** A new column was added in BOTH alembic migration 039 (`op.add_column`) and main.py's runtime `_run_migrations`. During a dev `--reload`, `_run_migrations` added the column without advancing `alembic_version`, so on the next container start the entrypoint's `alembic upgrade head` re-ran `op.add_column` on the existing column → `DuplicateColumnError` → crash loop.
**Rule for next time:** This codebase has TWO migration mechanisms (alembic `versions/` AND `main.py._run_migrations`). When a schema change is added to both, the alembic migration MUST be idempotent — use `op.execute("ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...")` (and `DROP ... IF EXISTS`) rather than `op.add_column`/`op.drop_*`, because the runtime layer can apply it first without bumping `alembic_version`.

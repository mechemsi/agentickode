---
title: Docker major image upgrades
status: implemented
date: 2026-11-15
related: [frontend-upgrades-2026-11-15.md, dependency-upgrades-2026-11-15.md]
---

# Changes and review

Applied in order: Node 24 to 26, PostgreSQL 16 to 18, Redis 7 to 8.
All three tags use multi-platform digest pins resolved through Docker Hub's
registry on 2026-11-15. Both frontend Dockerfiles and both Compose base files
agree, since the Compose files share named volumes. Volume names are preserved.
Both frontend builds now copy the existing package-lock.json and use npm ci.
Docker digests lock the image dependencies. JavaScript manifests and lockfiles
need no regeneration because no application dependency changed.

Reviewed every crossed major using official sources:

- Node [25 release/removals](https://nodejs.org/en/blog/release/v25.0.0),
  [26 release/removals](https://nodejs.org/en/blog/release/v26.0.0), and
  [deprecation histories/replacements](https://nodejs.org/api/deprecations.html).
  Frontend tooling has no uses of removed SlowBuffer, legacy stream modules,
  recursive rmdir or writeHeader. Browser localStorage is qualified with window.
  No Alpine package, user or extension adjustments were needed. Dependencies
  still need execution on Node 26 in CI.
- PostgreSQL [17 release/migration](https://www.postgresql.org/docs/17/release-17.html),
  [17 upgrade guide](https://www.postgresql.org/docs/17/upgrading.html),
  [18 release/migration](https://www.postgresql.org/docs/18/release-18.html),
  [18 upgrade guide](https://www.postgresql.org/docs/18/upgrading.html), and
  [image PGDATA changes](https://github.com/docker-library/docs/blob/master/postgres/README.md#pgdata).
  Models, repositories, Alembic and connection configuration have no custom
  maintenance functions, affected interval syntax, generated columns, MD5
  configuration or removed settings requiring adaptation. New clusters enable
  checksums by default; pg_upgrade requires matching checksum settings.
- Redis [8.0 release notes](https://github.com/redis/redis/blob/8.0/00-RELEASENOTES)
  and [standalone upgrade guide](https://redis.io/docs/latest/operate/oss_and_stack/install/upgrade/standalone/).
  QueueService uses hashes, sets, deletion and untyped SCAN, with RESP2 already
  explicit. GETRANGE changes, typed SCAN optimization and obsolete threading
  settings do not affect it. No custom ACLs or modules are configured.
  The /data mount remains correct. No client package bumps were needed.

CI now uses Node 26 and pinned PostgreSQL 18, runs for changes to these
Docker definitions, and builds the frontend alongside type checking.

# Existing data migration required before startup

PostgreSQL's mount changes from /var/lib/postgresql/data to /var/lib/postgresql.
PGDATA defaults to /var/lib/postgresql/18/docker. Empty volumes initialize
normally. Existing PostgreSQL 16 data cannot be opened by 18. The official
entrypoint detects PG_VERSION at the old volume root and refuses initialization.
Moving files alone does not upgrade the database format.

1. Before switching images, stop application writers and export the version 16
   database using pg_dump and roles using pg_dumpall --globals-only. Store these
   outside the volume. Stop PostgreSQL and take an offline copy of
   agentickode-app_pgdata. Do not use compose down -v.
2. Rehearse a logical restore into a separate empty PostgreSQL 18 staging volume
   mounted at /var/lib/postgresql. Restore required roles and the application
   database using PostgreSQL 18 tools with SQL errors treated as failures.
   Check migrations, row counts and application reads/writes.
3. After verification, with both databases stopped, archive the old volume
   contents outside the volume and copy the verified staging volume's 18/docker
   tree into agentickode-app_pgdata, preserving ownership and modes. Keep the
   original backup. Start the updated stack and check health and application
   behavior before resuming writers. Alternatively use pg_upgrade with both
   versions' binaries, first using --check and matching checksum settings.
4. Rollback requires stopping writers and restoring the version 16 offline
   backup together with the old image and mount definitions. Version 16 cannot
   read version 18 data. Later writes need separate reconciliation.

For Redis, stop writers, run redis-cli SAVE on version 7, and copy persistence
files outside agentickode-app_redisdata before stopping it. Start 8 against the
retained /data mount and check persisted queue entries and queue operations.
Rollback requires the version 7 backup and old image; do not assume version 7
can read files rewritten by 8. These migration procedures are untested here.
No database or Redis data was changed.

# Validation

- Docker Hub registry lookups resolved all target tags to their manifest digests.
- YAML and static assertions check image pins, shared volume layouts, preserved
  names, CI versions, Dockerfile lock usage and manifest/lock consistency.
- The existing user-event lock root range (^14.6.9) differs from the manifest
  (^14.5.2); its locked version satisfies both. No unrelated lock edits made.
- python3 scripts/check_alembic_heads.py passed with single head 044.
- node --check frontend/scripts/check-complexity.mjs passed on host Node 22.
- pytest and Ruff probes failed because neither is installed. Frontend
  node_modules, TypeScript, ESLint and Vitest are absent. No host npm commands
  were run under the repository's Docker execution rule.
- Docker is unavailable. Image builds, Node 26 execution, application tests,
  lint/type checks and live PostgreSQL/Redis migration/health checks remain
  unverified locally. CI results are pending; Redis tests currently mock Redis.

# Verification of the supplied repository

The supplied snapshot already contained all upgrades described above, including
matching dev images, CI versions, and the PostgreSQL volume migration. No image,
application dependency, or lockfile changes were needed during this verification.
Reviewed the linked upstream release and migration notes again for Node 25 and
26, PostgreSQL 17 and 18, and Redis 8. Registry requests independently confirmed
that all three existing digest pins match the requested Docker Hub tags.

Re-ran static assertions for matching image pins, PostgreSQL and Redis volume
layouts, preserved PostgreSQL volume names, and npm ci lockfile usage. Passed.
The Alembic single-head check and JavaScript syntax check passed again.
The queue unit-test probe and Ruff probe could not run: their Python modules
are absent. PyYAML and frontend node_modules are also absent, so YAML parsing,
frontend lint, type checking, tests and build were not re-run. Docker builds,
live service compatibility and data migration remain unverified. No host npm
commands, commits, pushes or branch operations were performed.

---
title: Docker major image upgrades
status: implemented
date: 2026-11-15
related: [frontend-upgrades-2026-11-15.md, dependency-upgrades-2026-11-15.md]
---

# Changes and review

Applied in order: Node 24 to 26, Redis 7 to 8. The PostgreSQL 16 to 18 part
of this change was reverted on 2026-11-17: database major upgrades are prepared
for a person to finish, not merged by the update agent. PostgreSQL stays on 16
(digest-pinned) with the volume at /var/lib/postgresql/data.
The tags use multi-platform digest pins resolved through Docker Hub's
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
- Redis [8.0 release notes](https://github.com/redis/redis/blob/8.0/00-RELEASENOTES)
  and [standalone upgrade guide](https://redis.io/docs/latest/operate/oss_and_stack/install/upgrade/standalone/).
  QueueService uses hashes, sets, deletion and untyped SCAN, with RESP2 already
  explicit. GETRANGE changes, typed SCAN optimization and obsolete threading
  settings do not affect it. No custom ACLs or modules are configured.
  The /data mount remains correct. No client package bumps were needed.

CI now uses Node 26, runs for changes to these
Docker definitions, and builds the frontend alongside type checking.

# Existing Redis data

For Redis, stop writers, run redis-cli SAVE on version 7, and copy persistence
files outside agentickode-app_redisdata before stopping it. Start 8 against the
retained /data mount and check persisted queue entries and queue operations.
Rollback requires the version 7 backup and old image; do not assume version 7
can read files rewritten by 8. These migration procedures are untested here.
No Redis data was changed.

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
  lint/type checks and live Redis migration/health checks remain
  unverified locally. CI results are pending; Redis tests currently mock Redis.

# Verification of the supplied repository

The supplied snapshot already contained all upgrades described above, including
matching dev images and CI versions. No image,
application dependency, or lockfile changes were needed during this verification.
Reviewed the linked upstream release and migration notes again for Node 25 and
26 and Redis 8. Registry requests independently confirmed
that the existing digest pins match the requested Docker Hub tags.

Re-ran static assertions for matching image pins, Redis volume layout, and npm ci lockfile usage. Passed.
The Alembic single-head check and JavaScript syntax check passed again.
The queue unit-test probe and Ruff probe could not run: their Python modules
are absent. PyYAML and frontend node_modules are also absent, so YAML parsing,
frontend lint, type checking, tests and build were not re-run. Docker builds,
live service compatibility and data migration remain unverified. No host npm
commands, commits, pushes or branch operations were performed.

---
title: Release Checklist
---

# Release Checklist

## When to Use
When preparing and shipping a new version release.

## Steps

### 1. Run full quality checks
```bash
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/
docker compose -f docker-compose.dev.yml exec backend ruff format --check backend/ tests/
docker compose -f docker-compose.dev.yml exec backend pyright backend/
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -v
docker compose -f docker-compose.dev.yml exec frontend npm run lint
docker compose -f docker-compose.dev.yml exec frontend npm test
```

### 2. Bump version
Update `frontend/package.json` version field.

### 3. Update IMPLEMENTATION_LOG.md
Add entry to `docs/IMPLEMENTATION_LOG.md` with date, version, summary, files changed, tests.

### 4. Commit and tag
```bash
git add -A
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

### 5. Verify
- Check GitHub Actions CI passes
- Verify the release tag appears on GitHub

## Common Issues

| Problem | Fix |
|---------|-----|
| CI fails after tag | Fix the issue, delete the tag, re-tag after fix |
| Forgot to bump version | Amend the commit and re-tag |
| License header missing | Run CI check, add headers to flagged files |

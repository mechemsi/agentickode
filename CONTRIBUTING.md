# Contributing to AgenticKode

Thank you for your interest in contributing to AgenticKode! This guide will help you get started.

## Contributor License Agreement

All contributors must agree to our [CLA](CLA.md) before contributions can be merged. When you open your first PR, a bot will ask you to confirm your agreement by commenting on the PR.

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Git

### Development Setup

```bash
# Clone the repository
git clone https://github.com/mechemsi/agentickode.git
cd agentickode

# Copy environment config
cp .env.example .env

# Start the dev environment
docker compose -f docker-compose.dev.yml up -d
```

### Running Tests

```bash
# Backend tests
docker compose -f docker-compose.dev.yml exec backend pytest tests/ -v

# Frontend tests
docker compose -f docker-compose.dev.yml exec frontend npm test
```

### Linting and Type Checking

```bash
# Backend
docker compose -f docker-compose.dev.yml exec backend ruff check backend/ tests/ --fix
docker compose -f docker-compose.dev.yml exec backend ruff format backend/ tests/
docker compose -f docker-compose.dev.yml exec backend pyright backend/

# Frontend
docker compose -f docker-compose.dev.yml exec frontend npm run lint
```

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/add-gitlab-webhook` — new features
- `fix/pipeline-retry-logic` — bug fixes
- `docs/update-webhook-guide` — documentation

### License Headers

All source files must include the license header. CI will fail if headers are missing.

**Python files:**
```python
# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com
```

**TypeScript files:**
```typescript
// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com
```

### Code Style

- **Backend**: Follow Ruff formatting and linting rules. Use async/await, Pydantic schemas, SQLAlchemy models.
- **Frontend**: Follow ESLint rules. Use TypeScript, functional React components.
- **Max 200 lines per file.** Split if larger.
- **All new features must have tests.** Maintain 70%+ coverage.
- Follow existing patterns in the codebase.

### Commit Messages

Write clear commit messages that describe the *why*, not just the *what*:

```
Add GitLab webhook support for merge request events

Previously only issue events triggered runs. This adds support for
merge request events so AgenticKode can respond to PR-related webhooks.
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure all checks pass: lint, type check, tests
4. Open a PR with a clear description
5. Sign the CLA when prompted
6. Address review feedback
7. Once approved, a maintainer will merge your PR

### PR Description Template

```markdown
## Summary
Brief description of what this PR does.

## Changes
- Change 1
- Change 2

## Testing
How you tested these changes.
```

## Architecture Guidelines

- **GitProvider Protocol**: Use for all git operations. Never call provider APIs directly.
- **RoleAdapter Protocol**: Use for all AI agent interactions.
- **ServiceContainer**: Worker phases receive services via dependency injection.
- **Repository Pattern**: Use for all database access. No inline queries in route handlers.
- **SSH for workspaces**: All workspace server interactions go through `SSHService`.

See [CLAUDE.md](CLAUDE.md) for detailed architecture rules.

## Reporting Bugs

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or screenshots
- Your environment (Docker version, OS)

## Questions?

Open a discussion or issue on GitHub.

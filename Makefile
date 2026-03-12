DC = docker compose -f docker-compose.dev.yml

# ── Dev environment ──────────────────────────────────────────
.PHONY: up down build restart logs

up:
	$(DC) up -d

down:
	$(DC) down

build:
	$(DC) up -d --build

restart:
	$(DC) restart

logs:
	$(DC) logs -f

logs-backend:
	$(DC) logs -f backend

logs-frontend:
	$(DC) logs -f frontend

# ── Backend ──────────────────────────────────────────────────
.PHONY: test test-cov test-file lint lint-fix fmt typecheck check shell-backend

test:
	$(DC) exec backend pytest tests/ -v

test-cov:
	$(DC) exec backend pytest tests/ --cov=backend --cov-report=term-missing

test-file:
	@test -n "$(F)" || (echo "Usage: make test-file F=tests/unit/test_pipeline.py" && exit 1)
	$(DC) exec backend pytest $(F) -v

lint:
	$(DC) exec backend ruff check backend/ tests/

lint-fix:
	$(DC) exec backend ruff check backend/ tests/ --fix

fmt:
	$(DC) exec backend ruff format backend/ tests/

typecheck:
	$(DC) exec backend pyright backend/

check: lint-fix fmt typecheck test

shell-backend:
	$(DC) exec backend bash

# ── Frontend ─────────────────────────────────────────────────
.PHONY: ftest ftest-cov flint flint-fix shell-frontend

ftest:
	$(DC) exec frontend npm test

ftest-cov:
	$(DC) exec frontend npm run test:coverage

flint:
	$(DC) exec frontend npm run lint

flint-fix:
	$(DC) exec frontend npm run lint:fix

shell-frontend:
	$(DC) exec frontend bash

# ── Database ─────────────────────────────────────────────────
.PHONY: migrate migrate-new db-shell

migrate:
	$(DC) exec backend alembic upgrade head

migrate-new:
	@test -n "$(MSG)" || (echo "Usage: make migrate-new MSG='add_users_table'" && exit 1)
	$(DC) exec backend alembic revision --autogenerate -m "$(MSG)"

db-shell:
	$(DC) exec postgres psql -U autodev -d autodev

# ── CI (mirrors GitHub Actions) ──────────────────────────────
.PHONY: ci ci-backend ci-frontend ci-push

ci-backend:
	@echo "=== Backend: lint ==="
	$(DC) exec backend ruff check backend/ tests/
	@echo "=== Backend: format check ==="
	$(DC) exec backend ruff format --check backend/ tests/
	@echo "=== Backend: type check ==="
	$(DC) exec backend pyright backend/
	@echo "=== Backend: tests ==="
	$(DC) exec backend pytest tests/ -v --cov=backend --cov-report=term-missing

ci-frontend:
	@echo "=== Frontend: lint ==="
	$(DC) exec frontend npm run lint
	@echo "=== Frontend: type check ==="
	$(DC) exec frontend npx tsc -b
	@echo "=== Frontend: tests ==="
	$(DC) exec frontend npm run test:coverage

ci: ci-backend ci-frontend
	@echo "=== All CI checks passed ==="

ci-push: ci
	git push

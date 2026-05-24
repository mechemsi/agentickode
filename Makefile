# ── Traefik routing toggle ───────────────────────────────────
# Hub running → routed overlay (http://autodev.localhost, http://autodev-api.localhost)
# Hub down    → fallback overlay (http://localhost:5173, http://localhost:8222)
TRAEFIK_RUNNING := $(shell docker inspect -f '{{.State.Running}}' traefik 2>/dev/null)

ifeq ($(TRAEFIK_RUNNING),true)
  COMPOSE_OVERLAY := -f docker-compose.traefik.yml
  TRAEFIK_MODE    := routed via Traefik
  ACCESS_FRONTEND := http://autodev.localhost
  ACCESS_BACKEND  := http://autodev-api.localhost
else
  COMPOSE_OVERLAY := -f docker-compose.fallback.yml
  TRAEFIK_MODE    := fallback (direct port)
  ACCESS_FRONTEND := http://localhost:5173
  ACCESS_BACKEND  := http://localhost:8222
endif

DC = docker compose -f docker-compose.dev.yml $(COMPOSE_OVERLAY)

# ── Dev environment ──────────────────────────────────────────
.PHONY: up down build restart logs traefik-info

traefik-info:
	@echo "Traefik:  $(if $(filter true,$(TRAEFIK_RUNNING)),running,not running)"
	@echo "Mode:     $(TRAEFIK_MODE)"
	@echo "Frontend: $(ACCESS_FRONTEND)"
	@echo "Backend:  $(ACCESS_BACKEND)"

up:
	$(DC) up -d
	@$(MAKE) --no-print-directory traefik-info

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
	$(DC) exec -e PYTHONPATH=/app backend alembic upgrade head

migrate-new:
	@test -n "$(MSG)" || (echo "Usage: make migrate-new MSG='add_users_table'" && exit 1)
	$(DC) exec -e PYTHONPATH=/app backend alembic revision --autogenerate -m "$(MSG)"

db-shell:
	$(DC) exec postgres psql -U agentickode -d agentickode

# ── Git hooks ────────────────────────────────────────────────
.PHONY: hooks

hooks:
	bash scripts/setup-hooks.sh

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

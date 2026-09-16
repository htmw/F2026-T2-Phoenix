# Single entry point for the checks CI runs, so "works locally" and "passes CI" mean
# the same thing.

.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND_VENV := backend/.venv/bin

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---- Environment ----

.PHONY: env
env: ## Create .env from the template if it does not exist
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

.PHONY: up
up: env ## Start the full stack
	$(COMPOSE) up --build

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and delete its volumes (destroys local data)
	$(COMPOSE) down --volumes

.PHONY: logs
logs: ## Tail logs from all services
	$(COMPOSE) logs -f

.PHONY: ps
ps: ## Show service status
	$(COMPOSE) ps

# ---- Local backend development ----

.PHONY: install
install: ## Install backend and frontend dependencies locally
	python3 -m venv backend/.venv
	$(BACKEND_VENV)/pip install --upgrade pip
	$(BACKEND_VENV)/pip install -r backend/requirements-dev.txt
	cd frontend && npm ci

.PHONY: format
format: ## Format backend code
	cd backend && .venv/bin/ruff format .

.PHONY: lint
lint: ## Lint backend and frontend
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npm run lint

.PHONY: typecheck
typecheck: ## Type-check backend and frontend
	cd backend && .venv/bin/mypy
	cd frontend && npm run typecheck

.PHONY: test
test: ## Run backend tests
	cd backend && .venv/bin/pytest

.PHONY: check
check: lint typecheck test ## Run every quality gate

# ---- Database ----

.PHONY: migrate
migrate: ## Apply migrations to the development database
	cd backend && .venv/bin/alembic upgrade head

.PHONY: migration
migration: ## Generate a migration from model changes (make migration m="add x")
	cd backend && .venv/bin/alembic revision --autogenerate -m "$(m)"

.PHONY: downgrade
downgrade: ## Roll back one migration
	cd backend && .venv/bin/alembic downgrade -1

.PHONY: test-db
test-db: ## Create the database used by integration tests
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-agentorch} -d postgres \
		-c "CREATE DATABASE $${POSTGRES_DB:-agentorch}_test OWNER $${POSTGRES_USER:-agentorch}" \
		|| echo "test database already exists"

# ---- Containerised equivalents ----

.PHONY: test-docker
test-docker: ## Run backend tests inside the backend container
	$(COMPOSE) run --rm --no-deps backend pytest

.PHONY: shell
shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend bash

.PHONY: psql
psql: ## Open a psql session against the development database
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-agentorch} -d $${POSTGRES_DB:-agentorch}

.PHONY: build-prod
build-prod: ## Build the production images
	docker build -t agentorch-backend:local ./backend
	docker build -t agentorch-frontend:local ./frontend

.PHONY: e2e
e2e: ## Run Playwright browser smoke (stack must be Demo Mode — no live provider keys)
	cd frontend && npm run test:e2e

.PHONY: e2e-ci
e2e-ci: env ## Compose with Demo Mode overlay, wait, Playwright, tear down
	$(COMPOSE) -f docker-compose.yml -f docker-compose.e2e.yml up --build -d
	@echo "Waiting for backend readiness…"
	@for i in $$(seq 1 60); do \
		if curl -sf http://localhost:$${BACKEND_PORT:-8000}/readyz | grep -q '"status":"ready"'; then \
			echo "Backend ready."; break; \
		fi; \
		if [ $$i -eq 60 ]; then echo "Backend not ready in time"; $(COMPOSE) logs --tail=80; exit 1; fi; \
		sleep 2; \
	done
	@echo "Waiting for frontend…"
	@for i in $$(seq 1 60); do \
		if curl -sf -o /dev/null http://localhost:$${FRONTEND_PORT:-3000}/; then \
			echo "Frontend ready."; break; \
		fi; \
		if [ $$i -eq 60 ]; then echo "Frontend not ready in time"; $(COMPOSE) logs --tail=80 frontend; exit 1; fi; \
		sleep 2; \
	done
	cd frontend && npm ci && npx playwright install --with-deps chromium && npm run test:e2e
	$(COMPOSE) -f docker-compose.yml -f docker-compose.e2e.yml down

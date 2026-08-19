# bitrix-internal-actors — developer commands
# Usage: make <target>   (e.g. make run-coo)

# Load .env so DB/broker/NIM vars are available to targets
ifneq (,$(wildcard .env))
include .env
export
endif

.DEFAULT_GOAL := help
.PHONY: help install sync infra-up infra-down migrate \
        run-coo run-employees run-internal-messaging run-staff-portal run-audit \
        run-local test lint format typecheck check clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Setup ---
sync:  ## Install all deps (uv)
	uv sync --extra dev

install: sync  ## Alias for sync

# --- Local infra (Postgres, Redis, broker) ---
infra-up:  ## Start Postgres, Redis, Kafka via docker compose
	docker compose up -d

infra-down:  ## Stop infra
	docker compose down

migrate:  ## Apply DB migrations
	uv run alembic upgrade head

# --- Run services (each is a FastAPI app; ports are illustrative) ---
run-coo:  ## Run the COO agent service
	uv run uvicorn services.coo.app.main:app --reload --port 8001

run-employees:  ## Run the employee agents service
	uv run uvicorn services.employees.app.main:app --reload --port 8002

run-internal-messaging:  ## Run the Internal Messaging service
	uv run uvicorn services.internal_messaging.app.main:app --reload --port 8085

run-local:  ## One command: start internal chat + seed + employee (SQLite, needs EMPLOYEE_OPENAI_API_KEY)
	python scripts/run_local.py

run-staff-portal:  ## Run the Staff Portal service
	uv run uvicorn services.staff_portal.app.main:app --reload --port 8004

run-audit:  ## Run the Audit / replay service
	uv run uvicorn services.audit.app.main:app --reload --port 8005

# --- Quality ---
test:  ## Run the test suite
	uv run pytest -q

lint:  ## Lint with Ruff
	uv run ruff check .

format:  ## Auto-format with Black + Ruff import sort
	uv run black .
	uv run ruff check --fix .

typecheck:  ## Static type check
	uv run mypy packages services

check: lint typecheck test  ## Run lint + typecheck + tests

clean:  ## Remove caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache

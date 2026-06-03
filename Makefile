.PHONY: bootstrap doctor dev test lint typecheck migrate start stop worker backup install

PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
PYTEST := $(VENV)/bin/pytest
ALEMBIC := $(VENV)/bin/alembic

bootstrap:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@if [ ! -f .env ]; then cp .env.example .env; fi
	@echo "Bootstrap complete. Run 'make start' then 'make migrate'."

doctor:
	@bash scripts/doctor.sh

dev:
	$(UVICORN) apps.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	DATABASE_URL=sqlite+aiosqlite:///:memory: $(PYTEST) tests/ -v

lint:
	$(RUFF) check .
	$(RUFF) format --check .

typecheck:
	$(MYPY) nova_core apps/api apps/worker

migrate:
	$(ALEMBIC) upgrade head

start:
	docker compose -f infra/docker-compose.yml up -d

stop:
	docker compose -f infra/docker-compose.yml down

worker:
	$(PY) -m apps.worker.main

backup:
	@bash scripts/backup.sh

install:
	$(PIP) install -e ".[dev]"

format:
	$(RUFF) format .
	$(RUFF) check --fix .

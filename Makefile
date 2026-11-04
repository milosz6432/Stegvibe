# SPECTRA developer tasks. POSIX shell assumed; see README.md for the equivalent plain commands.
PY      ?= python3
VENV    ?= .venv
BIN      = $(VENV)/bin

.PHONY: help setup build run dev-backend dev-frontend test test-backend test-frontend lint typecheck clean

help:
	@echo "setup          create $(VENV), install backend (+dev tools) and frontend dependencies"
	@echo "build          build the frontend into frontend/dist"
	@echo "run            serve API + built UI on http://127.0.0.1:8000"
	@echo "dev-backend    API with auto-reload on :8000"
	@echo "dev-frontend   Vite dev server on :5173 (proxies /api to :8000)"
	@echo "test           backend + frontend tests"
	@echo "lint           ruff (lint + format check) and the TypeScript type-check"
	@echo "clean          remove build output and caches (keeps $(VENV), node_modules and your data)"

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e "backend[dev]"
	cd frontend && npm install

build:
	cd frontend && npm run build

run:
	$(BIN)/python -m spectra

dev-backend:
	$(BIN)/uvicorn spectra.main:create_app --factory --reload --reload-dir backend/spectra --host 127.0.0.1 --port 8000

dev-frontend:
	cd frontend && npm run dev

test: test-backend test-frontend

test-backend:
	cd backend && ../$(BIN)/python -m pytest

test-frontend:
	cd frontend && npm test

typecheck:
	cd frontend && npm run typecheck

lint: typecheck
	cd backend && ../$(BIN)/ruff check . && ../$(BIN)/ruff format --check .

clean:
	rm -rf frontend/dist backend/.pytest_cache backend/.ruff_cache backend/build
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +

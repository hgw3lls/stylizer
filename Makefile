SHELL := /bin/bash

.PHONY: dev dev-web dev-api test test-web test-api lint lint-web lint-api format format-web format-api build build-web build-api

dev:
	@echo "Starting API and web dev servers..."
	@(cd apps/api && uv run uvicorn app.main:app --reload --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000}) & \
	(cd apps/web && npm run dev -- --host 0.0.0.0)

dev-web:
	cd apps/web && npm run dev -- --host 0.0.0.0

dev-api:
	cd apps/api && uv run uvicorn app.main:app --reload --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000}

test: test-web test-api

test-web:
	cd apps/web && npm run test

test-api:
	cd apps/api && uv run pytest

lint: lint-web lint-api

lint-web:
	cd apps/web && npm run lint

lint-api:
	cd apps/api && uv run ruff check .

format: format-web format-api

format-web:
	cd apps/web && npm run format

format-api:
	cd apps/api && uv run black . && uv run ruff check . --fix

build: build-web build-api

build-web:
	cd apps/web && npm run build

build-api:
	cd apps/api && uv run python -m compileall app

# AGENTS.md — style-translator

Follow these rules when editing this repository.

## Core rules
- Keep changes minimal, focused, and consistent with existing patterns.
- Prefer small diffs in one area (`apps/web`, `apps/api`, or `shared`) at a time.
- Do not introduce new dependencies unless they are required.
- Run unit tests before finishing any task.
- Update docs when behavior, commands, env vars, or contracts change.

## Repository map
- `apps/web`: React + Vite + TypeScript + Tailwind frontend.
- `apps/api`: FastAPI backend (Python 3.12, uv, Pydantic).
- `shared`: cross-app Style Pack contract artifacts.

## Style Pack schema (source of truth)
- Canonical schema: `shared/style_pack.schema.json`.
- Example payload: `shared/style-pack.example.json`.
- Contract notes: `shared/README.md`.

When adding Style Pack fields:
1. Add the field to `shared/style_pack.schema.json` (required/type/constraints).
2. Update `shared/style-pack.example.json` with a valid example.
3. Update API models in `apps/api/app/schemas.py`.
4. Update web types in `apps/web/src/types.ts`.
5. Update tests affected by the new field.

## Commands
Run from repo root unless noted.

### Root shortcuts
- `make dev` — run API + web dev servers.
- `make test` — run web + API unit tests.
- `make lint` — run web + API lint checks.
- `make format` — run web + API formatters.
- `make build` — build web and compile-check API.

### Web (`apps/web`)
- `npm run dev` — start Vite dev server.
- `npm run test` — run vitest unit tests.
- `npm run lint` — run eslint.
- `npm run format` — run prettier.
- `npm run build` — typecheck + production build.

### API (`apps/api`)
- `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` — start API dev server.
- `uv run pytest` — run pytest unit tests.
- `uv run ruff check .` — lint Python code.
- `uv run black . && uv run ruff check . --fix` — format and auto-fix.
- `uv run python -m compileall app` — compile-check app package.

## Environment variables
Copy `.env.example` to `.env` for local development.

Required baseline vars:
- `APP_ENV`
- `API_HOST`
- `API_PORT`
- `API_CORS_ORIGINS`
- `VITE_API_URL`

If working on OpenAI image generation, set:
- `OPENAI_API_KEY` — API key for OpenAI calls.
- `OPENAI_IMAGE_MODEL` — image model name (for example `gpt-image-1`).
- `OPENAI_IMAGE_SIZE` — output size (for example `1024x1024`).
- `OPENAI_IMAGE_QUALITY` — output quality mode (for example `high`).

## Local image storage (dev)
- Store generated images under `apps/api/data/images/` during local development.
- Use dated or request-scoped subfolders to avoid collisions.
- Do not commit generated binaries; keep them out of git.

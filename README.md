# style-translator

Production-ready monorepo skeleton for translating and persisting style packs.

## Repository layout
- `apps/web` — React + Vite + TypeScript + Tailwind frontend with React Query + Zod.
- `apps/api` — FastAPI backend using Python 3.12, `uv`, Pydantic, and SQLite via SQLAlchemy.
- `shared` — Style Pack schema and shared types/docs.

## Prerequisites
- Node.js 20+
- npm 10+
- Python 3.12+
- `uv` installed (`pip install uv`)
- Docker (optional)

## Setup
1. Copy environment variables:
   ```bash
   cp .env.example .env
   ```
2. Install web dependencies:
   ```bash
   cd apps/web && npm install
   ```
3. Install API dependencies:
   ```bash
   cd ../api && uv sync --dev
   ```

## Local development
From repo root:
```bash
make dev
```

Run independently:
```bash
make dev-api
make dev-web
```

- Web: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

## Core API endpoints
- `POST /style-packs` (multipart): `name` + one or more `images`
- `GET /style-packs`
- `GET /style-packs/{id}`
- `POST /style-packs/{id}/analyze` (analyzes stored images via OpenAI and saves `constraints` + `prompt_anchors`)
- `POST /translate` (sync multipart translation with style pack + input image anchor)
- `POST /jobs/translate` (async job creation; returns `job_id` immediately)
- `GET /jobs/{id}` (job status + result)

Uploaded images are stored under `apps/api/data/assets/{style_pack_id}/...` in local dev (configurable with `ASSETS_ROOT`).

## Contract and strict validation
- Canonical schema: `shared/style_pack.schema.json`
- TS types: `shared/style_pack.ts`
- API Pydantic models reject unknown fields via strict config.

## Testing, linting, formatting, builds
```bash
make test
make lint
make format
make build
```

## Docker local development
```bash
cp .env.example .env
docker compose up --build
```


## OpenAI analysis configuration
Set `OPENAI_API_KEY` and `OPENAI_ANALYSIS_MODEL` in `.env` before using `/style-packs/{id}/analyze`.


## Translate endpoint
`POST /translate` accepts multipart fields: `style_pack_id`, `mode` (`translate_single` or `synthesize_multi`), `input_images[]`, and JSON `options`.
- `translate_single`: first input image is the source anchor.
- `synthesize_multi`: requires 2–10 input images, creates a Fusion Plan, perturbs plan fields per variation, and generates outputs per plan.

The API validates mime type/size server-side, builds a final prompt from style-pack anchors+constraints+options, calls OpenAI image generation, and returns base64 images with metadata.

Set `OPENAI_API_KEY`, `OPENAI_ANALYSIS_MODEL`, and `OPENAI_IMAGE_MODEL` in `.env` for analysis/translation.


`synthesize_multi` options include `fusion_strategy` (`collage` | `poseA_bgB` | `motif_fusion`) and optional `dominance_weights`.


## UI pages
- `Style Packs`: create packs, list packs, inspect details, and run analysis.
- `Translate`: choose pack, choose mode, set controls, submit job, poll status, render/download outputs.
- `History`: inspect recent translation jobs and outputs saved by API in SQLite.

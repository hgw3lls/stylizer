# style-translator

Production-ready monorepo skeleton for translating and persisting style packs.

## Repository layout
- apps/web — React + Vite + TypeScript + Tailwind frontend with React Query + Zod.
- apps/api — FastAPI backend using Python 3.12, uv, Pydantic, and SQLite via SQLAlchemy.
- shared — Style Pack schema and shared types/docs.

## Prerequisites
- Node.js 20+
- npm 10+
- Python 3.12+
- uv installed (pip install uv)
- Docker (optional)

## Setup

Copy environment variables:
```
cp .env.example .env
```

Install web dependencies:
```
cd apps/web && npm install
```

Install API dependencies:
```
cd ../api && uv sync --dev
```

## Local development

From repo root:
```
make dev
```

Run independently:
```
make dev-api
make dev-web
```

Web: http://localhost:5173  
API docs: http://localhost:8000/docs

## Core API endpoints

- POST /style-packs (multipart): name + one or more images
- GET /style-packs
- GET /style-packs/{id}
- POST /style-packs/{id}/analyze (analyzes stored images via OpenAI and saves constraints + prompt_anchors)
- GET /style-packs/{id}/export (downloads a zip with style_pack.json + all style images)
- POST /style-packs/import (upload a style-pack zip and recreate it locally)
- POST /translate (sync multipart translation with style pack + input image anchor)
- POST /jobs/translate (async job creation; returns job_id immediately)
- GET /jobs/{id} (job status + result)

Uploaded images are stored under apps/api/data/assets/{style_pack_id}/... in local dev (configurable with ASSETS_ROOT).

## Contract and strict validation
- Canonical schema: shared/style_pack.schema.json
- TS types: shared/style_pack.ts
- API Pydantic models reject unknown fields via strict config.

## Testing, linting, formatting, builds
```
make test
make lint
make format
make build
```

## Docker local development
```
cp .env.example .env
docker compose up --build
```

## OpenAI analysis configuration
Set OPENAI_API_KEY and OPENAI_ANALYSIS_MODEL in .env before using /style-packs/{id}/analyze.

The API auto-selects the first available model from a preference list by calling `GET /v1/models` and caching results for 5 minutes. Set `OPENAI_ANALYSIS_MODEL` to force a preferred analysis model when available.

## Translate endpoint

POST /translate accepts multipart fields: style_pack_id, mode (translate_single or synthesize_multi), input_images[], and JSON options.

translate_single: first input image is the source anchor.

synthesize_multi: requires 2–10 input images, creates a Fusion Plan, perturbs plan fields per variation, and generates outputs per plan.

The API validates mime type/size server-side, builds a final prompt from style-pack anchors + constraints + options, calls OpenAI image generation, and returns base64 images with metadata.

Set OPENAI_API_KEY, OPENAI_ANALYSIS_MODEL, and OPENAI_IMAGE_MODEL in .env for analysis/translation.

For image generation, the API resolves `OPENAI_IMAGE_MODEL` against available models. If no compatible image model is available to the key/project, image generation is disabled and the API logs a warning.

Set `DEBUG=1` to enable `GET /debug/models` for local debugging. This endpoint returns available model ids, selected analysis model, and selected image model.

synthesize_multi options include fusion_strategy (collage | poseA_bgB | motif_fusion) and optional dominance_weights.

## UI pages

Style Packs: create packs, list packs, inspect details, and run analysis.

Translate: choose pack, choose mode, set controls, submit job, poll status, render/download outputs.

History: inspect recent translation jobs and outputs saved by API in SQLite.

## Local verification checklist (OpenAI model selection)

1. Start API:
   ```bash
   cd apps/api
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. Check health:
   ```bash
   curl -s http://localhost:8000/health
   ```
   Expected: JSON with `{"status":"ok"...}`.
3. (Optional when `DEBUG=1`) inspect model selection:
   ```bash
   curl -s http://localhost:8000/debug/models | jq '{available_model_count,selected_analysis_model,selected_image_model,truncated}'
   ```
   Expected: selected model ids and count/truncation metadata.
4. Create + analyze a style pack:
   ```bash
   curl -s -X POST http://localhost:8000/style-packs \
     -F "name=verify-pack" \
     -F "images=@/path/to/style.png;type=image/png"

   curl -s -X POST http://localhost:8000/style-packs/<STYLE_PACK_ID>/analyze
   ```
   Expected: style pack JSON with populated `constraints` and `prompt_anchors`.
5. Create translate job and poll status:
   ```bash
   curl -s -X POST http://localhost:8000/jobs/translate \
     -F "style_pack_id=<STYLE_PACK_ID>" \
     -F "mode=translate_single" \
     -F 'options={"size":"1024x1024","quality":"high","variations":1,"preserve_composition":true}' \
     -F "input_images=@/path/to/input.png;type=image/png"

   curl -s http://localhost:8000/jobs/<JOB_ID>
   ```
   Expected:
   - success path: `status=completed` and result images, or
   - disabled path: `status=failed` with message containing `No image generation model available for this API key/project`.
6. Ensure no model-not-found error appears:
   ```bash
   curl -s http://localhost:8000/jobs/<JOB_ID> | jq -r '.error_message // ""'
   ```
   Expected: does **not** contain `model_not_found`.

For a one-command automated local check, run:
```bash
./apps/api/scripts/verify_local_dev.sh
```

## Prompt hardening behavior

Prompt generation enforces style lock constraints on every request:

- The final prompt always includes constraints.forbidden plus hard guardrails: No hybridization and No drift outside constraints.
- A style-lock directive is injected to prevent drift outside style-pack constraints.
- Variability controls (drift, density, abstraction) are clamped to [0, 1] before prompt assembly.
- The negative prompt from prompt_anchors.negative_prompt is always included for translate and synthesis flows.
- Final prompts are logged with sensitive data redacted (API keys and inline user image data URLs).

## Sharing style packs between machines

You can export/import style packs as a zip bundle to move them between environments.

Export from source machine:
```
curl -L -o style-pack.zip http://localhost:8000/style-packs/<STYLE_PACK_ID>/export
```

Import on destination machine:
```
curl -X POST http://localhost:8000/style-packs/import \
  -F "archive=@style-pack.zip;type=application/zip"
```

The archive includes:
- style_pack.json manifest (name/version/constraints/prompt anchors)
- images/* style image files

On import, the API creates a new style pack ID and stores images under the configured ASSETS_ROOT.

#!/usr/bin/env bash
set -euo pipefail

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
API_BASE="http://${API_HOST}:${API_PORT}"

# 1x1 transparent PNG
PNG_B64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+3k8AAAAASUVORK5CYII="
TMP_DIR="$(mktemp -d)"
IMG1="${TMP_DIR}/style-1.png"
IMG2="${TMP_DIR}/input-1.png"
cleanup() {
  if [[ -n "${UVICORN_PID:-}" ]] && kill -0 "${UVICORN_PID}" 2>/dev/null; then
    kill "${UVICORN_PID}" || true
  fi
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

echo "${PNG_B64}" | base64 -d > "${IMG1}"
cp "${IMG1}" "${IMG2}"

echo "Starting uvicorn on ${API_BASE}..."
(
  cd "$(dirname "$0")/.."
  uv run uvicorn app.main:app --host "${API_HOST}" --port "${API_PORT}" >/tmp/stylizer-api.log 2>&1
) &
UVICORN_PID=$!

# Wait for health
for _ in {1..40}; do
  if curl -sf "${API_BASE}/health" >/dev/null; then
    break
  fi
  sleep 0.5
done
curl -sf "${API_BASE}/health" | jq .

echo "\n[optional] /debug/models (requires DEBUG=1)"
DEBUG_STATUS="$(curl -s -o /tmp/debug-models.out -w '%{http_code}' "${API_BASE}/debug/models")"
if [[ "${DEBUG_STATUS}" == "200" ]]; then
  jq '{available_model_count, selected_analysis_model, selected_image_model, truncated}' /tmp/debug-models.out
else
  echo "debug/models disabled (HTTP ${DEBUG_STATUS})"
fi

echo "\nCreating style pack..."
CREATE_JSON="$(curl -sf -X POST "${API_BASE}/style-packs" \
  -F "name=local-verify-pack" \
  -F "images=@${IMG1};type=image/png")"
STYLE_PACK_ID="$(echo "${CREATE_JSON}" | jq -r '.id')"
echo "style_pack_id=${STYLE_PACK_ID}"

echo "\nAnalyzing style pack..."
curl -sf -X POST "${API_BASE}/style-packs/${STYLE_PACK_ID}/analyze" | jq '{id,name,constraints,prompt_anchors}'

echo "\nCreating translate job..."
OPTIONS='{"size":"1024x1024","quality":"high","variations":1,"preserve_composition":true}'
JOB_JSON="$(curl -sf -X POST "${API_BASE}/jobs/translate" \
  -F "style_pack_id=${STYLE_PACK_ID}" \
  -F "mode=translate_single" \
  -F "options=${OPTIONS}" \
  -F "input_images=@${IMG2};type=image/png")"
JOB_ID="$(echo "${JOB_JSON}" | jq -r '.job_id')"
echo "job_id=${JOB_ID}"

echo "\nPolling job status..."
for _ in {1..60}; do
  STATUS_JSON="$(curl -sf "${API_BASE}/jobs/${JOB_ID}")"
  STATUS="$(echo "${STATUS_JSON}" | jq -r '.status')"
  if [[ "${STATUS}" == "completed" || "${STATUS}" == "failed" ]]; then
    break
  fi
  sleep 1
done
echo "${STATUS_JSON}" | jq '{status,error_message,result_present:(.result!=null)}'

echo "\nVerifying no model_not_found..."
if echo "${STATUS_JSON}" | jq -e '.error_message // "" | test("model_not_found")' >/dev/null; then
  echo "ERROR: model_not_found detected"
  exit 1
fi

if echo "${STATUS_JSON}" | jq -e '.status=="failed" and ((.error_message // "") | test("No image generation model available"))' >/dev/null; then
  echo "Image generation disabled as expected (HTTP 503 path translated into job failure message)."
elif echo "${STATUS_JSON}" | jq -e '.status=="completed"' >/dev/null; then
  echo "Image generation completed successfully."
else
  echo "Unexpected terminal status."
  exit 1
fi

echo "\nDone."

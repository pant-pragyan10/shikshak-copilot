#!/usr/bin/env bash
# Local dev entrypoint: bring up infra, then run the API with autoreload.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Starting infrastructure (qdrant)…"
docker compose up -d qdrant

echo "==> Launching API on http://localhost:8000 (reload)…"
exec uvicorn teacher_copilot.api.main:app --reload --host 0.0.0.0 --port 8000

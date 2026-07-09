#!/usr/bin/env bash
# Run the Teacher Copilot API locally with autoreload.
#
#   ./scripts/run_api.sh            # http://localhost:8000  (docs at /docs)
#
# Needs provider keys in .env for live LLM calls. Startup is fast — the ~2GB embedder
# loads lazily on the first lesson-plan/career (RAG) request.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

exec uvicorn teacher_copilot.api.main:app --reload --host 0.0.0.0 --port "${PORT:-8000}"

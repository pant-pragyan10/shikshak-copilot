# Backend image for Teacher Copilot (FastAPI + embedded Qdrant + local embeddings).
#
# Docker isn't required on the dev machine — the HOST (Render/Railway/Fly) builds this
# remotely. It's a fairly large image because sentence-transformers pulls in torch;
# that's the cost of running embeddings locally (no embedding API, full privacy).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/data/hf

WORKDIR /app

# Install the package (deps resolved from pyproject).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# Ship the sample corpus + career dataset so RAG can be ingested on the host.
COPY data ./data
COPY scripts ./scripts

# Embedded Qdrant + profiles live on a mounted disk in production (see render.yaml).
ENV QDRANT_PATH=/data/qdrant \
    PROFILE_STORE_PATH=/data/profiles

EXPOSE 8000

# Respect the platform's $PORT if provided.
CMD ["sh", "-c", "uvicorn teacher_copilot.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

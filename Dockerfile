# SMO-19 · Ingestion worker image for the Cloud Run job sg-ingest-worker (ADR-011)
#   gcloud builds submit --tag europe-west1-docker.pkg.dev/storegear-prod-ag26/storegear/ingest-worker:v1
# Dependencies come from uv.lock (same versions as the laptop). No data, no secrets: identity is sg-ingestion.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY ingestion/ ingestion/
ENV STOREGEAR_RUNNING_AS_SA=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
CMD ["/app/.venv/bin/python", "ingestion/worker.py"]

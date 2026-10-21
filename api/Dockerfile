# SMO-22 · sg-api image (ADR-014). Built from the repo root:
#   gcloud builds submit --config api/cloudbuild.yaml
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/ api/
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
CMD ["/app/.venv/bin/uvicorn", "--app-dir", "api", "main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN useradd --create-home --uid 10001 appuser

COPY pyproject.toml ./
COPY app ./app
RUN pip install .

COPY alembic.ini ./
COPY alembic ./alembic

USER appuser
EXPOSE 8000

# Migrations are idempotent, so running them on every start is safe (also after a free-tier restart).
CMD ["sh", "-c", "python -m app.cli migrate && python -m app.cli seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

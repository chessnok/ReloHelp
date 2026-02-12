ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-cache

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY tests ./tests
COPY scripts ./scripts

# Make scripts executable
RUN chmod +x scripts/*.sh

EXPOSE 8000
# Use init script as entrypoint
ENTRYPOINT ["/app/scripts/init.sh"]
CMD ["uv", "run", "uvicorn", "app.main:app", "--port", "8000", "--host", "0.0.0.0"]
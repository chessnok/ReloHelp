ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml ./

RUN uv sync --no-cache

COPY app ./app

EXPOSE 8001
CMD ["uv", "run", "python", "-m", "app.run_server"]

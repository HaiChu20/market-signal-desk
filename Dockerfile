FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.12 /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY live.toml ./live.toml
RUN uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/live \
    && chown -R app:app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1
USER app
CMD ["python", "-m", "msd.live.engine", "--live"]

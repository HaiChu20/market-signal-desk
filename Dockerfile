FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.12 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends cargo rustc \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY rust/msd_kernels ./rust/msd_kernels
RUN uv sync --frozen --no-dev \
    && uvx --from maturin==1.16.0 maturin build --release --locked \
         --manifest-path rust/msd_kernels/Cargo.toml --out /tmp/wheels \
    && uv pip install --python /app/.venv/bin/python /tmp/wheels/*.whl \
    && find /app/.venv -name '_msd_kernels*.so' -exec cp {} /app/src/msd/ \;

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY src ./src
COPY --from=builder /app/src/msd/_msd_kernels.abi3.so ./src/msd/
COPY live.toml ./live.toml
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/live \
    && chown -R app:app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    MSD_REQUIRE_RUST=1
USER app
HEALTHCHECK --interval=60s --timeout=5s --start-period=2m --retries=3 \
    CMD python -c "from pathlib import Path; import time,sys; p=Path('/app/data/live/heartbeat'); sys.exit(0 if p.exists() and time.time()-p.stat().st_mtime < 180 else 1)"
CMD ["python", "-m", "msd.live.engine", "--live"]

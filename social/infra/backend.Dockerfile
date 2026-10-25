FROM ghcr.io/astral-sh/uv:0.13.5 AS uv
FROM python:3.12.14-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev && useradd --create-home --uid 10001 appuser && mkdir -p /app/storage/avatars && chmod 700 /app/storage/avatars && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "steamscope_social.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers", "--ws-max-size", "1024", "--ws-max-queue", "16"]

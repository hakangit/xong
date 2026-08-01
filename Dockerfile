FROM python:3.14-slim-bookworm AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_SYSTEM_CERTS=1
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
COPY alembic.ini README.md SPEC.md ./
COPY alembic ./alembic
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

FROM python:3.14-slim-bookworm
WORKDIR /app
COPY --from=build /app /app
# static trilingual frontend (web PWA; same code Tauri wraps)
COPY clients/web/ui /app/ui
ENV PATH="/app/.venv/bin:$PATH" XONG_STATIC_DIR=/app/ui
EXPOSE 8000
CMD ["uvicorn", "xong.app:app", "--host", "0.0.0.0", "--port", "8000"]

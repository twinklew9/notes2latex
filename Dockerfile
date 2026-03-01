# Stage 1: Build frontend
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Backend + serve
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-base texlive-latex-recommended texlive-latex-extra \
    texlive-fonts-recommended texlive-science texlive-pictures \
    latexmk && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable

COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

COPY --from=frontend /app/frontend/dist frontend/dist

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["notes2latex", "serve"]

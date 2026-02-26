FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-base texlive-latex-recommended texlive-latex-extra \
    texlive-fonts-recommended texlive-science texlive-pictures \
    latexmk && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/
ENTRYPOINT ["uv", "run", "notes2latex"]

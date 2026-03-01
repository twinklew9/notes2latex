# notes2latex

Convert handwritten math notes to compiled LaTeX using vision LLMs.

## Local Development

**Prerequisites:** Python 3.12+, Node.js 22+, [uv](https://docs.astral.sh/uv/), a LaTeX distribution (`texlive-latex-extra`, `latexmk`)

```bash
# Install backend dependencies
make install

# Install frontend dependencies
cd frontend && npm install && cd ..

# Create .env with your API key (optional — can also configure in the UI)
echo 'OPENROUTER_API_KEY=sk-...' > .env
```

Run the backend and frontend dev servers in separate terminals:

```bash
# Terminal 1: backend (port 8000)
make serve

# Terminal 2: frontend with hot reload (port 5173, proxies API to 8000)
make dev-frontend
```

### Other commands

```bash
make test          # run tests
make lint          # ruff check
make format        # ruff format
make docker-build  # build Docker image
```

### Docker

```bash
docker compose up --build
```

The app is served at `http://localhost:8000`.

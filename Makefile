.PHONY: help install dev dev-backend dev-frontend build up down test lint format clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies for local development
	uv sync
	cd frontend && npm install

dev: ## Run backend and frontend dev servers
	trap 'kill 0' EXIT; $(MAKE) dev-backend & $(MAKE) dev-frontend & wait

dev-backend: ## Run backend dev server
	uv run notes2latex serve

dev-frontend: ## Run frontend dev server
	cd frontend && npm run dev

build: ## Build Docker image
	docker compose build

up: ## Start services via Docker Compose
	docker compose up -d

down: ## Stop services
	docker compose down

test: ## Run tests
	uv run pytest -v

lint: ## Run linter
	uv run ruff check src/ tests/

format: ## Format code
	uv run ruff format src/ tests/

clean: ## Remove build artifacts and caches
	rm -rf frontend/dist .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

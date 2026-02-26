.PHONY: install test lint format run docker-build

# Clear PYTHONPATH to prevent system packages (e.g. ROS) from leaking into the venv
unexport PYTHONPATH

install:
	uv sync

test:
	PYTHONPATH= uv run pytest -v

lint:
	PYTHONPATH= uv run ruff check src/ tests/

format:
	PYTHONPATH= uv run ruff format src/ tests/

run:
	PYTHONPATH= uv run notes2latex $(ARGS)

docker-build:
	docker build -t notes2latex .

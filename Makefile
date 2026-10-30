# Run each long-running target in its own terminal: temporal, worker, api, web.

.PHONY: install temporal worker api web test lint

install:
	cd backend && uv sync
	cd frontend && npm install

temporal:
	mkdir -p .dev && temporal server start-dev --db-filename .dev/temporal.db --ui-port 8233

worker:
	cd backend && uv run python -m app.worker

api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest --cov=app --cov-report=term-missing

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

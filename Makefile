.PHONY: install up down logs test lint format rag-ingest seed agent-test eval clean build deploy db-upgrade db-revision

install:
	./scripts/bootstrap.sh

## `up`/`down` target real docker compose. In network-restricted sandboxes
## where Docker Hub pulls are blocked, use scripts/dev_native.sh instead.
up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	./scripts/test.sh

lint:
	cd agent-service && . .venv/bin/activate && ruff check app tests && mypy app

format:
	cd agent-service && . .venv/bin/activate && ruff format app tests

rag-ingest:
	cd agent-service && . .venv/bin/activate && python -m app.rag.pipeline

db-upgrade:
	cd agent-service && . .venv/bin/activate && alembic upgrade head

db-revision:
	cd agent-service && . .venv/bin/activate && alembic revision --autogenerate -m "$(m)"

seed:
	./scripts/seed_data.sh

agent-test:
	cd agent-service && . .venv/bin/activate && python -m tests.demo_scenarios

## Behavioral eval against the real agent graph — see tests/eval_agent.py.
## Runs against the real configured LLM (small real cost) when an API key
## is set, otherwise falls back to a FakeLLM dry run (free, mechanics only).
eval:
	cd agent-service && . .venv/bin/activate && python -m tests.eval_agent

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf agent-service/.pytest_cache mock-enterprise/.pytest_cache

build:
	docker compose build

deploy:
	./scripts/deploy.sh

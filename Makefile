.PHONY: dev dev-api dev-web db-up db-down migrate migration test lint fmt gen-api create-user bot worker install vapid-keys

COMPOSE = docker compose -f docker-compose.dev.yml --env-file .env
BACK = cd backend && uv run

install:
	cd backend && uv sync
	cd frontend && npm install

db-up:
	$(COMPOSE) up -d --wait db

db-down:
	$(COMPOSE) down

dev: db-up migrate
	$(MAKE) -j2 dev-api dev-web

dev-api:
	$(BACK) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	cd frontend && npm run dev

migrate:
	$(BACK) alembic upgrade head

# make migration m="add users"
migration:
	$(BACK) alembic revision --autogenerate -m "$(m)"

test:
	$(BACK) pytest

lint:
	$(BACK) ruff check .
	$(BACK) ruff format --check .
	cd frontend && npx oxlint && npx tsc -b --noEmit

fmt:
	$(BACK) ruff check --fix .
	$(BACK) ruff format .

gen-api:
	$(BACK) python -m scripts.dump_openapi ../frontend/openapi.json
	cd frontend && npx openapi-typescript openapi.json -o src/api/schema.d.ts

# make create-user email=me@example.com
create-user:
	$(BACK) python -m app.cli create-user $(email)

bot:
	$(BACK) python -m app.bot

worker:
	$(BACK) python -m app.worker

# Ключи Web Push -> скопировать в .env
vapid-keys:
	$(BACK) python -m app.cli vapid-keys

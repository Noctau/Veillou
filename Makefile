.PHONY: dev dev-api dev-web db-up db-down migrate migration test lint fmt gen-api create-user bot worker install vapid-keys \
	deploy prod-ps prod-logs prod-create-user prod-backup prod-restore backup-pull

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

# ---------- прод (Docs/DEPLOY.md): DEPLOY_HOST / DEPLOY_DIR в .env ----------
REMOTE = source infra/remote.sh && remote

deploy:
	./infra/deploy.sh

prod-ps:
	@bash -c '$(REMOTE) "$$COMPOSE ps"'

# make prod-logs s=api   (без s — все сервисы)
prod-logs:
	@bash -c '$(REMOTE) -t "$$COMPOSE logs -f --tail=200 $(s)"'

# make prod-create-user email=...
prod-create-user:
	@bash -c '$(REMOTE) -t "$$COMPOSE run --rm api python -m app.cli create-user $(email)"'

# Бэкап прямо сейчас (обычно — каждый день в 04:00 сам)
prod-backup:
	@bash -c '$(REMOTE) "$$COMPOSE exec -T backup /scripts/backup.sh"'

# make prod-restore b=2026-10-07_040000   (или b=latest)
prod-restore:
	@bash -c '$(REMOTE) -t "./infra/restore.sh $(b)"'

# Серверные бэкапы → BACKUP_LOCAL_DIR на маке (по умолчанию ~/Backups/veillou)
backup-pull:
	./infra/backup-pull.sh

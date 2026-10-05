# Veillou

Личный планировщик учёбы и жизни. Контекст — [Docs/CONTEXT.md](Docs/CONTEXT.md), план — [Docs/DEV_PLAN.md](Docs/DEV_PLAN.md).

## Быстрый старт

Нужны: Docker, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
cp .env.example .env
make install
make dev          # Postgres 16 (docker, :5433) + миграции + API :8000 + фронт :5173
```

| Команда | Что делает |
|---|---|
| `make dev` | БД, миграции, API и фронт с hot-reload |
| `make migrate` / `make migration m="..."` | применить / создать миграцию |
| `make test` | pytest (БД `veillou_test` в том же контейнере) |
| `make lint` / `make fmt` | ruff + tsc / автоформат |
| `make gen-api` | OpenAPI бэкенда → `frontend/src/api/schema.d.ts` |

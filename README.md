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
| `make create-user email=...` | создать пользователя (пароль спросит; регистрации в приложении нет) |
| `make bot` | Telegram-бот (long polling), нужен `TELEGRAM_BOT_TOKEN` в `.env` |
| `make worker` | фоновый процесс: напоминания (push + Telegram), пересборка, ночная докатка |
| `make vapid-keys` | ключи Web Push → вписать в `.env` |

Telegram: создать бота у @BotFather, вписать `TELEGRAM_BOT_TOKEN` и `TELEGRAM_BOT_USERNAME`
в `.env`, запустить `make bot`, затем «Настройки → Telegram → Привязать».

Напоминания: `make vapid-keys` → `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` в `.env`, запустить
`make worker`, затем «Настройки → Уведомления → Включить» (push работает на https или localhost)
и «Проверить уведомления». Без воркера напоминания не уходят.

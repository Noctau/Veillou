#!/usr/bin/env bash
# Восстановление на сервере (запускается там, из DEPLOY_DIR):
#   ./infra/restore.sh 2026-10-07_040000 | latest
# С мака: make prod-restore b=latest
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=${1:?Укажите бэкап: имя каталога в BACKUP_DIR или latest}
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env"

read -r -p "БД и файлы будут заменены бэкапом «$NAME». Продолжить? [y/N] " answer
[ "$answer" = y ] || [ "$answer" = Y ] || { echo "Отменено"; exit 1; }

$COMPOSE stop api worker bot
trap '$COMPOSE start api worker bot' EXIT
$COMPOSE run --rm backup /scripts/restore.sh "$NAME"

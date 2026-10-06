#!/usr/bin/env bash
# Общее для скриптов, которые ходят на сервер: DEPLOY_HOST / DEPLOY_DIR из окружения или .env.
#   source infra/remote.sh; remote "docker compose ... ps"
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

_from_env_file() {
  # Только DEPLOY_*/BACKUP_* — остальной .env (dev-настройки) не трогаем
  [ -f .env ] || return 0
  local line
  while IFS= read -r line; do
    case "$line" in
      DEPLOY_HOST=* | DEPLOY_DIR=* | BACKUP_DIR=* | BACKUP_LOCAL_DIR=*)
        local key=${line%%=*}
        [ -z "${!key:-}" ] && export "$line"
        ;;
    esac
  done < .env
}
_from_env_file

: "${DEPLOY_HOST:?Укажите DEPLOY_HOST=user@host в .env (см. Docs/DEPLOY.md)}"
DEPLOY_DIR=${DEPLOY_DIR:-/srv/veillou/app}
BACKUP_DIR=${BACKUP_DIR:-/srv/veillou/backups}
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env"

# remote "команда" — выполнить в DEPLOY_DIR на сервере; remote -t … — с терминалом (пароль, логи)
remote() {
  local tty=()
  if [ "${1:-}" = "-t" ]; then tty=(-t); shift; fi
  ssh "${tty[@]}" "$DEPLOY_HOST" "cd '$DEPLOY_DIR' && $*"
}

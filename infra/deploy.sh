#!/usr/bin/env bash
# make deploy: исходники → сервер (rsync), сборка и перезапуск там же.
# Миграции применяет сервис migrate до старта api/worker/bot. .env на сервере не трогается.
source "$(dirname "$0")/remote.sh"

if [ -n "$(git status --porcelain)" ]; then
  echo "⚠️  Есть незакоммиченные изменения — они тоже уедут на сервер."
fi
REV=$(git rev-parse --short HEAD)
echo "→ $DEPLOY_HOST:$DEPLOY_DIR ($REV)"

ssh "$DEPLOY_HOST" "mkdir -p '$DEPLOY_DIR' && test -f '$DEPLOY_DIR/.env'" || {
  echo "На сервере нет $DEPLOY_DIR/.env — создайте его из .env.prod.example (Docs/DEPLOY.md)"
  exit 1
}

rsync -az --delete \
  --include='/.env.prod.example' --exclude='/.git' --exclude='/.env' --exclude='/.env.*' \
  --exclude='/.idea' --exclude='/.claude' --exclude='/venv' --exclude='/data' \
  --exclude='node_modules' --exclude='/frontend/dist' --exclude='.venv' \
  --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='.DS_Store' \
  ./ "$DEPLOY_HOST:$DEPLOY_DIR/"
ssh "$DEPLOY_HOST" "echo $REV > '$DEPLOY_DIR/REVISION'"

remote "$COMPOSE up -d --build --remove-orphans && docker image prune -f >/dev/null"

echo "→ жду api…"
for _ in $(seq 1 30); do
  if remote "$COMPOSE exec -T api python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=3)\"" 2>/dev/null; then
    remote "$COMPOSE ps --format 'table {{.Service}}\t{{.Status}}'"
    echo "✓ $REV на сервере"
    exit 0
  fi
  sleep 3
done
echo "✗ api не ответил за 90 с. Логи: make prod-logs s=api"
remote "$COMPOSE ps"
exit 1

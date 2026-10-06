#!/bin/sh
# Восстановление из бэкапа: БД целиком заменяется дампом, файлы — снапшотом.
#   restore.sh 2026-10-07_040000 | latest
# Запускать через infra/restore.sh (останавливает api/worker/bot на время восстановления).
set -eu
[ -f /etc/backup.env ] && . /etc/backup.env

NAME=${1:?Укажите бэкап: имя каталога из /backups или latest}
if [ "$NAME" = latest ]; then
  SRC=$(ls -1d /backups/20* 2>/dev/null | tail -n 1 || true)
else
  SRC="/backups/$NAME"
fi
if [ -z "$SRC" ] || [ ! -f "$SRC/OK" ] || [ ! -f "$SRC/db.dump" ]; then
  echo "Нет целого бэкапа: ${SRC:-/backups пуст}" >&2
  ls -1 /backups >&2 || true
  exit 1
fi

export PGPASSWORD="$POSTGRES_PASSWORD"
echo "Восстанавливаю БД $POSTGRES_DB из $SRC"
pg_restore -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists --no-owner --single-transaction "$SRC/db.dump"

echo "Восстанавливаю файлы"
rsync -a --delete "$SRC/files/" /data/files/
echo "Готово: $SRC"

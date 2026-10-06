#!/bin/sh
# Бэкап: БД (pg_dump -Fc) + файлы. Файлы — снапшот с хардлинками на предыдущий
# (rsync --link-dest): неизменившиеся файлы место не занимают, каждый снапшот полный.
# Хранится BACKUP_KEEP последних (по умолчанию 14 — две недели ежедневных).
#   /backups/2026-10-07_040000/{db.dump,files/,OK}
set -eu
[ -f /etc/backup.env ] && . /etc/backup.env

ROOT=/backups
KEEP=${BACKUP_KEEP:-14}
STAMP=$(date +%Y-%m-%d_%H%M%S)
TMP="$ROOT/.tmp-$STAMP"
export PGPASSWORD="$POSTGRES_PASSWORD"

log() { echo "$(date '+%F %T') backup: $*"; }

rm -rf "$ROOT"/.tmp-*
mkdir -p "$TMP"
chmod 700 "$ROOT" "$TMP"
# files/ внутри — как в томе (644/755): читается владельцем снапшота, чужим закрыто каталогом 700

log "БД $POSTGRES_DB → $STAMP"
pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$TMP/db.dump"
pg_restore -l "$TMP/db.dump" > /dev/null  # дамп читается целиком

PREV=$(ls -1d "$ROOT"/20* 2>/dev/null | tail -n 1 || true)
if [ -n "$PREV" ] && [ -d "$PREV/files" ]; then
  rsync -a --link-dest="$PREV/files" /data/files/ "$TMP/files/"
else
  rsync -a /data/files/ "$TMP/files/"
fi

echo "$STAMP" > "$TMP/OK"
mv "$TMP" "$ROOT/$STAMP"

# Ротация: оставляем KEEP последних
COUNT=$(ls -1d "$ROOT"/20* | wc -l)
if [ "$COUNT" -gt "$KEEP" ]; then
  ls -1d "$ROOT"/20* | head -n $((COUNT - KEEP)) | while read -r old; do
    log "удаляю $old"
    rm -rf "$old"
  done
fi

# Владелец каталогов и дампа — пользователь сервера, чтобы `make backup-pull` мог читать
# (каталоги 700, чужим не видно). Дерево files/ не трогаем: другой владелец —
# и rsync --link-dest перестанет узнавать файлы, каждый снапшот станет полной копией.
chmod 600 "$ROOT/$STAMP/db.dump"
if [ -n "${BACKUP_UID:-}" ]; then
  owner="$BACKUP_UID:${BACKUP_GID:-$BACKUP_UID}"
  chown "$owner" "$ROOT" "$ROOT/$STAMP" "$ROOT/$STAMP/db.dump" "$ROOT/$STAMP/OK"
fi

log "готово: $(du -sh "$ROOT/$STAMP/db.dump" | cut -f1) БД, всего $(du -sh "$ROOT" | cut -f1) на $(ls -1d "$ROOT"/20* | wc -l) снапшотов"

#!/usr/bin/env bash
# make backup-pull: зеркало серверных бэкапов на мак (хардлинки между снапшотами сохраняются).
source "$(dirname "$0")/remote.sh"
LOCAL=${BACKUP_LOCAL_DIR:-$HOME/Backups/veillou}
LOCAL=${LOCAL/#\~/$HOME}
mkdir -p "$LOCAL"
echo "→ $DEPLOY_HOST:$BACKUP_DIR → $LOCAL"
rsync -aH --delete --exclude='.tmp-*' "$DEPLOY_HOST:$BACKUP_DIR/" "$LOCAL/"
ls -1 "$LOCAL" | tail -n 3

#!/bin/sh
# cron запускает задания с пустым окружением — сохраняем нужные переменные для backup.sh
set -eu
export -p | grep -E "export (POSTGRES_|BACKUP_|TZ=)" > /etc/backup.env
chmod 600 /etc/backup.env
if [ "$#" -gt 0 ]; then exec "$@"; fi
echo "Бэкапы: каждый день в 04:00 ($TZ), хранится ${BACKUP_KEEP:-14}"
exec crond -f -l 6

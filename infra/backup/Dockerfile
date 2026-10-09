# pg_dump той же мажорной версии, что и сервер (16) + rsync для снапшотов файлов + cron (busybox)
FROM postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
RUN apk add --no-cache rsync tzdata
COPY backup.sh restore.sh entrypoint.sh /scripts/
COPY crontab /etc/crontabs/root
RUN chmod +x /scripts/*.sh
# root осознанно (AUDIT_REPORT.md, L-11): rsync --link-dest с сохранением владельцев,
# ротация снапшотов с файлами чужого uid, chown дампа на BACKUP_UID
# nosemgrep: dockerfile.security.missing-user-entrypoint.missing-user-entrypoint
ENTRYPOINT ["/scripts/entrypoint.sh"]

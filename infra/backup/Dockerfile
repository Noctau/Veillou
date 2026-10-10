# pg_dump той же мажорной версии, что и сервер (16) + rsync для снапшотов файлов + cron (busybox)
FROM postgres:18-alpine@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873
RUN apk add --no-cache rsync tzdata
COPY backup.sh restore.sh entrypoint.sh /scripts/
COPY crontab /etc/crontabs/root
RUN chmod +x /scripts/*.sh
# root осознанно (AUDIT_REPORT.md, L-11): rsync --link-dest с сохранением владельцев,
# ротация снапшотов с файлами чужого uid, chown дампа на BACKUP_UID
# nosemgrep: dockerfile.security.missing-user-entrypoint.missing-user-entrypoint
ENTRYPOINT ["/scripts/entrypoint.sh"]

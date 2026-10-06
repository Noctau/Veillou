# pg_dump той же мажорной версии, что и сервер (16) + rsync для снапшотов файлов + cron (busybox)
FROM postgres:16-alpine
RUN apk add --no-cache rsync tzdata
COPY backup.sh restore.sh entrypoint.sh /scripts/
COPY crontab /etc/crontabs/root
RUN chmod +x /scripts/*.sh
ENTRYPOINT ["/scripts/entrypoint.sh"]

#!/bin/sh
# Запуск Caddy не от root. Тома /data и /config могли быть созданы прежними версиями
# образа (от root) — сначала отдаём их пользователю caddy, потом сбрасываем права.
set -eu
chown -R caddy:caddy /data /config
exec su-exec caddy "$@"

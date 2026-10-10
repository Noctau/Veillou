# Фронт собирается здесь же: на сервере не нужен Node, а в образе Caddy — только статика.
# Базовые образы зафиксированы по digest (обновляет Dependabot).
FROM node:25-alpine@sha256:bdf2cca6fe3dabd014ea60163eca3f0f7015fbd5c7ee1b0e9ccb4ced6eb02ef4 AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/dist /srv/www
# Не root: 80/443 — через capability на бинарнике, права на тома — в entrypoint
RUN apk add --no-cache libcap su-exec \
    && addgroup -S caddy && adduser -S -G caddy -H -s /sbin/nologin caddy \
    && setcap cap_net_bind_service=+ep /usr/bin/caddy \
    && chown -R caddy:caddy /data /config
COPY --chmod=755 infra/caddy/entrypoint.sh /entrypoint.sh
# Без USER осознанно: entrypoint от root только отдаёт тома, затем su-exec caddy
# nosemgrep: dockerfile.security.missing-user-entrypoint.missing-user-entrypoint
ENTRYPOINT ["/entrypoint.sh"]
# nosemgrep: dockerfile.security.missing-user.missing-user
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]

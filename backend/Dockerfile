# Один образ на три процесса: api (по умолчанию), worker, bot — команда в docker-compose.prod.yml.
# Базовые образы зафиксированы по digest (обновляет Dependabot, .github/dependabot.yml).
FROM ghcr.io/astral-sh/uv:0.11@sha256:77280f2f771df71f90786c314fe1bbc1e023feac652969bbf139c280babf2eb7 AS uv

# ---------- сборка окружения: uv нужен только здесь ----------
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Зависимости отдельным слоем: пересобираются только при смене uv.lock
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
COPY . .

# ---------- рантайм: без uv и кэшей ----------
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    STORAGE_DIR=/data/files
WORKDIR /app
RUN useradd --system --uid 1000 app && mkdir -p /data/files && chown app /data/files
# Код и окружение принадлежат root: процесс app их читает, но не меняет
COPY --from=build /app /app
USER app

EXPOSE 8000
# Для api; у worker/bot/migrate свой healthcheck в docker-compose.prod.yml
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=3)"]
# X-Forwarded-* принимаются только из приватных сетей docker (там Caddy), не от кого угодно
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "172.16.0.0/12,192.168.0.0/16,10.0.0.0/8"]

# Деплой и бэкапы

Один VPS, Docker Compose: `db` (Postgres 16), `migrate` (Alembic, одноразовый), `api`, `worker`, `bot`,
`web` (Caddy: HTTPS + собранный фронт + прокси `/api`), `backup` (cron, 04:00).
Код приезжает с мака через rsync, а образы собираются прямо на сервере (`make deploy`).

## 1. Сервер (один раз)

Нужны VPS за рубежом (NL/FI/KZ), Ubuntu 24.04, ≥ 1 ГБ RAM и домен.

1. **DNS:** A-запись домена → IP сервера. Без неё Caddy не получит сертификат.
2. **Docker, файрвол, swap.** Swap нужен, чтобы на 1 ГБ RAM хватило памяти на `npm ci` и сборку фронта.
   ```bash
   ssh root@IP
   curl -fsSL https://get.docker.com | sh
   adduser deploy && usermod -aG docker deploy      # дальше работаем под deploy
   ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
   fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
   echo '/swapfile none swap sw 0 0' >> /etc/fstab
   mkdir -p /srv/veillou/app /srv/veillou/backups && chown -R deploy:deploy /srv/veillou
   ```
   Положить свой ssh-ключ в `~deploy/.ssh/authorized_keys`.
3. **Прод-`.env`** — на сервере, в git не попадает:
   ```bash
   scp .env.prod.example deploy@IP:/srv/veillou/app/.env
   ssh deploy@IP nano /srv/veillou/app/.env
   ```
   - `DOMAIN`, `ACME_EMAIL`.
   - `POSTGRES_PASSWORD` (`openssl rand -hex 24`), `SECRET_KEY` (`openssl rand -hex 32`).
   - `VAPID_*`: выполнить `make vapid-keys` на маке. Ключи генерируются один раз: если их сменить, все push-подписки перестанут работать.
   - `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME`. Long polling не даёт одному токену работать в двух местах сразу. Поэтому для dev заведите второго бота у @BotFather или не запускайте `make bot` локально, пока работает прод.
   - `BACKUP_UID` / `BACKUP_GID` — вывод `id -u` / `id -g` пользователя `deploy`.
4. **Локальный `.env` на маке** (берётся только скриптами `infra/*.sh`):
   ```
   DEPLOY_HOST=deploy@IP
   DEPLOY_DIR=/srv/veillou/app
   BACKUP_DIR=/srv/veillou/backups
   BACKUP_LOCAL_DIR=~/Backups/veillou
   ```

## 2. Первый запуск

```bash
make deploy                                  # rsync → build → up, ждёт /health
make prod-create-user email=user@example.com # пароль спросит
```
Открыть `https://DOMAIN` на телефоне и войти. При первом входе откроется онбординг: семестр → звонки →
пары → часы/сон → push → Telegram. Затем в меню Chrome выбрать «Добавить на главный экран»: так работают
офлайн-режим и «Поделиться» из других приложений.

## 3. Обычная жизнь

| Команда (с мака) | Что делает |
|---|---|
| `make deploy` | выкатить текущий код (миграции применятся сами) |
| `make prod-ps` | статус контейнеров |
| `make prod-logs s=api` | логи (`s=` — `api`, `worker`, `bot`, `web`, `backup`; без `s` — все) |
| `make prod-backup` | бэкап прямо сейчас |
| `make backup-pull` | забрать бэкапы с сервера на мак |
| `make prod-restore b=latest` | восстановить из бэкапа (спросит подтверждение) |

## 4. Бэкапы

- Запускаются каждый день в 04:00 по `DEFAULT_TIMEZONE`, после ночной джобы воркера. Пишутся в `BACKUP_DIR` на сервере:
  `2026-10-07_040000/{db.dump, files/, OK}`. Хранятся `BACKUP_KEEP` последних (14).
- `db.dump` — это `pg_dump -Fc`; сразу после записи он проверяется через `pg_restore -l`. `files/` — полный снапшот
  хранилища, но неизменившиеся файлы связаны хардлинками с предыдущим снапшотом и места почти не занимают.
- Каталог бэкапов закрыт правами 700 и принадлежит `deploy`.
- Копия на маке: `make backup-pull` зеркалит каталог в `BACKUP_LOCAL_DIR`, хардлинки сохраняются.
  Чтобы не забывать, можно повесить эту команду на ежедневное расписание через launchd или cron.

### Восстановление

```bash
make prod-restore b=latest          # или b=2026-10-07_040000 (имена — ls в BACKUP_DIR)
```
Скрипт останавливает `api`, `worker` и `bot`, полностью заменяет БД дампом (`pg_restore --clean`
в одной транзакции), синхронизирует файлы со снапшотом и запускает сервисы обратно.

**Проверка руками (DoD M7.4)** — после первого деплоя и затем раз в пару месяцев:
1. Добавить в приложении задание с фото.
2. `make prod-backup`, затем `make prod-restore b=latest`. Данные не теряются: бэкап только что сделан.
3. Убедиться, что задание и фото на месте.
4. `make backup-pull` — на маке появился тот же каталог.

### Переезд или новый сервер

Выполнить шаги 1–2 на новом сервере (без `prod-create-user`). Затем
`rsync -aH ~/Backups/veillou/ deploy@NEW:/srv/veillou/backups/`, `make prod-restore b=latest`
и переключить DNS.

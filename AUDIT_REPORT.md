# AUDIT_REPORT — Veillou

Фазы 1–2 аудита (код проекта не менялся). Дата: 2026-10-08, ветка `m13-projects-v2` @ `31943fa`.
Контекст и карта поверхности атаки — [AUDIT_CONTEXT.md](AUDIT_CONTEXT.md).

Доказательства, помеченные «пробник», получены одноразовыми pytest-скриптами вне репозитория
(на тестовой БД `veillou_test`, с фикстурами из `backend/tests/conftest.py`); их можно
превратить в падающие регрессионные тесты в Фазе 3.

## Итог

| Severity | Кол-во |
|---|---|
| CRITICAL | 0 |
| HIGH | 2 |
| MEDIUM | 12 |
| LOW | 22 |
| INFO | 10 |

**Топ-5 самых опасных**

1. **H-01** — логин без rate limit, argon2 считается в event loop: 60 параллельных неверных логинов
   поднимают латентность `/health` с 2 мс до 1.7 с (неаутентифицированный DoS + неограниченный перебор пароля).
2. **M-01** — тело запроса (JSON и multipart до 110 МБ) читается целиком **до** проверки сессии
   и до «лимита» `_limit_body` → исчерпание памяти/диска анонимом.
3. **M-04** — ReDoS в выдержке конспекта: `excerpt("[" * 199_000)` — **67 с** CPU в event loop на каждый `GET /notes`.
4. **M-06 / M-07** — нет идемпотентности: двойное «Применить план» создаёт дубли блоков,
   двойное «+15 мин» — два напоминания (подтверждено).
5. **M-02** — SSRF через `endpoint` push-подписки: воркер шлёт POST на любой `https://` URL
   и следует редиректам (в т. ч. во внутреннюю сеть `llm`).

Что в проекте сделано хорошо и подтверждено проверками: изоляция данных пользователей
(динамический IDOR-пробник: 117 запросов чужими id — 0 утечек, 0 изменений), безопасная раздача
файлов (allowlist inline-MIME + `nosniff` + `CSP: sandbox`), экранирование HTML в Telegram,
токены сессий/кнопок хранятся как sha256, параметризованный SQL и санитизация FTS-запроса,
aware-datetime везде, обратимые миграции, 90 % branch coverage бэкенда, 0 уязвимых Python-пакетов,
0 секретов в истории git.

---

## Фаза 1 — автоматический анализ

| Инструмент | Запуск | Результат | Классификация |
|---|---|---|---|
| ruff (конфиг проекта) | `ruff check .`, `ruff format --check .` | 0 / 226 файлов ок | — |
| ruff (E,F,W,I,B,UP,S,SIM,RUF,ASYNC,PT,N) | `--ignore RUF001,RUF002,RUF003` (кириллица) | 1927 | S101 ×1738: 1718 в тестах — ложные (assert в pytest), **20 в `app/` — реальные → L-16**; PT018 ×161, PT011 ×8 — стиль тестов (LOW, в L-15); S105/S106/S107 ×8 — тестовые пароли и `DEV_SECRET` (ложные: dev-значение, в проде запрещено валидатором `config.py:119`); S603, S311 — тесты (ложные); N802 `DATABASE_URL`, N805 `declared_attr cls` — ложные (идиомы pydantic/SQLAlchemy); N806 ×3 (`domain/tasks.py:19`), SIM102 ×2, SIM105, SIM300 ×2 — стиль (L-15) |
| mypy `--strict` | `uv run --with mypy mypy --strict app scripts` | 95 ошибок в 30 файлах | Корень большинства — неверная аннотация `UserScopedRepository.select()` (`services/base.py:29`, `Select[M]` vs `Select[tuple[M]]`) → каскад `tuple[Category] has no attribute id` и т. п. (ложные в рантайме); переиспользование переменных с разными типами (`reminder_actions.py:144/151`, `breakdown.py:304/319`, `quickparse.py:384/430/499`); `StrEnum` vs `str` сравнения. Проверено вручную ~15 мест, похожих на баги — рантайм-багов нет → L-15. Достижимый уровень сейчас: проектный ruff, mypy в CI не запускается |
| bandit | `uvx bandit -r app scripts` | 21 Low | 20 × B101 assert → L-16; 1 × B105 `DEV_SECRET` — ложное |
| pip-audit | по `uv export --locked` (76 пакетов, вкл. dev) | 0 уязвимостей | — |
| semgrep | `p/python p/fastapi p/security-audit p/secrets p/typescript p/react p/dockerfile p/docker-compose`, `--metrics=off` | 1 | `infra/backup/Dockerfile` без `USER` → L-11. `--config auto` не запускался: требует отправки метрик (заменён эквивалентными наборами) |
| gitleaks | `gitleaks git` по всей истории (44 коммита) | 0 утечек | `.env`, `.env.prod` никогда не коммитились; удалённые `Docs/` в истории — только плейсхолдеры |
| trivy fs | vuln + secret + misconfig | npm: braces HIGH, katex LOW; Dockerfile: нет HEALTHCHECK ×3 (LOW), root ×2 (backup, caddy) | braces → `shadcn` CLI, не попадает в бандл (L-12); katex — в бандле (L-12); root → L-11; HEALTHCHECK → L-19 (в compose для api есть) |
| trivy image | собранный `backend` | 94 HIGH/CRITICAL (3 CRITICAL в `perl-base`), 50 с готовым фиксом; Python-пакеты — 0 | Реальная проблема процесса сборки → M-10 |
| trivy image | локальные `caddy:2-alpine`, `postgres:16-alpine` | 40 HIGH (все с фиксом) / 22 HIGH+1 CRIT (`gosu`) | Устаревшие локальные копии тегов → M-10 |
| npm audit | `--omit=dev` | 11 (7 high, 4 low) | Та же цепочка braces→micromatch→fast-glob→`shadcn`/ts-morph (CLI) и katex 0.16.47 → L-12 |
| pytest --cov | branch, `concurrency=greenlet,thread` | 720 passed, **90 %** | Без `greenlet` coverage показывает 82 % (не видит код после переключений SQLAlchemy) → L-21 |
| vulture | `--min-confidence 60` | 30 | 26 ложных (атрибуты Pydantic/ORM, заполняемые динамически); **4 реальных мёртвых функции** → L-17 |
| deptry | `deptry .` | 12 | Реальные: прямые импорты без объявления `starlette`, `anyio`, `cryptography` → L-17; ложные: `uvicorn`, `asyncpg`, `python-multipart` (используются неявно), `python-dateutil`/`dateutil` (маппинг имени), `email_validator` (через `pydantic[email]`) |
| oxlint, tsc | фронт | 0 / 0 | — |

## Фаза 2 — ручной аудит: что проверено и чисто

| Пункт | Что смотрел | Итог |
|---|---|---|
| SQL-инъекции | все `execute`/`text()`; FTS (`domain/search.py:7,22`) | только ORM/Core и константные `text()`; ввод поиска сводится к `[^\W_]+` |
| Command injection, SSTI, десериализация | grep `subprocess`, `os.system`, `eval`, `pickle`, `yaml` | в `app/` нет; shell-скрипты принимают ввод только оператора |
| Path traversal | `core/storage.py:48-53`, `services/attachments.py:55-57` | ключ — sha256, `is_relative_to(root)`; имя файла очищается и квотируется в `Content-Disposition` |
| AuthZ / IDOR | пробник: A создаёт 20 видов объектов, B бьёт все 85 операций с path-id + 32 запроса с чужими id в теле/query | 0 утечек, 0 изменений состояния A; все 2xx — пустые списки или no-op |
| AuthN-поверхность | анонимный прогон всех 140 операций | без сессии отвечают ровно 5 ожидаемых |
| XSS через файлы | `api/attachments.py:93-107` | inline только картинки/pdf/txt/mp3/mp4, везде `nosniff`, кроме PDF — `CSP: sandbox` |
| XSS во фронте | grep `dangerouslySetInnerHTML`, `innerHTML`, `href=` | нет сырого HTML; `react-markdown` без `rehype-raw`; все URL-поля — `HttpUrl` на бэке |
| HTML в Telegram | `notify/message.py:70-75`, `bot/cards.py:57-58`, `bot/ai.py` | весь пользовательский текст через `html.escape` |
| Бот | `bot/middleware.py:31-44`, `services/telegram.py:52-80` | только личные чаты и привязанные id; код привязки 96 бит, одноразовый, `FOR UPDATE` |
| Сессии/cookie/CSRF | `api/deps.py:15-50`, `services/auth.py` | HttpOnly, Secure (прод), SameSite=Lax, токен в БД как sha256; JSON-тело требует `application/json` (FastAPI) |
| CORS | `main.py` | не включён (same-origin) — корректно |
| Секреты | gitleaks, trivy secret, `.gitignore` | чисто; `SECRET_KEY` по умолчанию запрещён в проде |
| Утечка ошибок | `core/exceptions.py`, `DEBUG` | стектрейсов наружу нет; `/docs` в проде не проксируется (Caddy отдаёт только `/api/*`) |
| Таймауты исходящих | LLM (`provider.py:287`), WebPush (`notifier.py:140`), aiogram | есть везде; солвер ограничен 2 с и вынесен в поток |
| Время | `UTCDateTime`, grep `datetime.now()`/`date.today()` | naive запрещены на уровне типа; в `app/` нет локального времени сервера |
| Миграции | round-trip на временной БД + `alembic check` | обратимы, соответствуют моделям |
| ReDoS в quickparse / вопросах экзамена | фаззинг 6000/50 000 символов | ≤ 10 мс |
| Prompt injection | `ai/schemas.py`, применение результатов | вывод модели валидируется схемами и попадает в черновики; см. I-09 |

## Находки

| ID | Severity | Категория | Файл:строка | Проблема | Воспроизведение / доказательство | Предлагаемый фикс | Риск фикса |
|---|---|---|---|---|---|---|---|
| H-01 | HIGH | Безопасность / DoS | `backend/app/core/security.py:17-21`, `backend/app/services/auth.py:44`, `backend/app/api/auth.py:15-27`, `backend/app/schemas/user.py:10` | Нет rate limit / блокировки перебора на `POST /auth/login`; argon2 `verify` (≈26 мс CPU) выполняется синхронно в event loop единственного процесса uvicorn → любой аноним останавливает весь API и может перебирать пароль без ограничений; длина пароля не ограничена | Пробник: `/health` 2.3 мс → **1698 мс** при 60 параллельных неверных логинах; замер `verify_password` ≈ 26 мс | `hash`/`verify` через `anyio.to_thread.run_sync`; лимит попыток на IP и на email (скользящее окно, ответ 429 + `Retry-After`); `max_length` пароля (например, 1024) | Низкий: поведение успешного логина не меняется; добавляется 429 |
| H-02 | HIGH | DX / сборка | `frontend/vite.config.ts:10-13`, `frontend/.gitignore:28`, `README.md:10-12` | `vite.config.ts` читает `frontend/openapi.json`, который в `.gitignore` → на чистом клоне `make dev` (быстрый старт из README) и сборка образа `web` падают | `git clone` → `npx vite build` → `ENOENT … frontend/openapi.json` | Хэшировать закоммиченный `src/api/schema.d.ts` (производное от той же схемы) вместо `openapi.json` | Низкий: один раз сбросится офлайн-кэш (buster) |
| M-01 | MEDIUM | Безопасность / DoS | `backend/app/api/attachments.py:29-32`, `infra/caddy/Caddyfile:18-19`; FastAPI `routing.py:439-463` (тело) раньше `:499` (зависимости) | Тело запроса читается целиком (JSON — в память, multipart — во временные файлы) до проверки сессии и до `_limit_body` (комментарий «до того, как тело ляжет во временный файл» неверен). Caddy пускает 110 МБ на **любой** путь, в dev лимита нет | Код FastAPI: `await request.body()/form()` до `solve_dependencies`; анонимный `POST /api/v1/tasks` с телом 110 МБ получает 401 только после чтения | ASGI-middleware с лимитом по пути (≈1 МБ для JSON, `MAX_UPLOAD_MB` только для `/attachments*`), проверка `Content-Length` и подсчёт потока; в Caddy — маленький `request_body` по умолчанию и 110 МБ только для загрузок | Низкий; проверить загрузки и share-target |
| M-02 | MEDIUM | Безопасность / SSRF | `backend/app/schemas/notify.py:23`, `backend/app/notify/notifier.py:129-141`, `docker-compose.prod.yml:62`; pywebpush `__init__.py:380` (`requests.post`, редиректы включены) | `endpoint` push-подписки проверяется только на `^https://`; воркер (подключён к сети `llm` со шлюзом туннеля Ollama) делает POST на любой хост и следует 307/308. Тело — шифротекст, ответ не возвращается (слепой SSRF), нужна сессия | `POST /me/push/subscriptions {"endpoint":"https://<любой хост>"...}` + `POST /me/notifications/test` → воркер ходит на указанный хост | Allowlist хостов push-сервисов (`fcm.googleapis.com`, `*.push.services.mozilla.com`, `*.notify.windows.com`, `*.push.apple.com`); `requests.Session` с отключёнными редиректами | Низкий; новые push-провайдеры — правкой списка |
| M-03 | MEDIUM | Безопасность / приватность | `frontend/src/features/auth/useAuthMutations.ts:22-33`, `backend/app/api/auth.py:30-34` | Выход не отписывает push: устройство продолжает получать напоминания пользователя (названия заданий, дедлайны) с кнопками, которые работают по токену без сессии | Код: `useLogout` чистит кэши, но не вызывает `/me/push/unsubscribe`; бэкенд при logout подписки не трогает | При выходе: взять текущую подписку SW → `POST /me/push/unsubscribe` до `/auth/logout` → `sub.unsubscribe()` | Низкий |
| M-04 | MEDIUM | Безопасность / ReDoS | `backend/app/domain/notes.py:35,44`, вызов `backend/app/services/notes.py:71`, лимит `backend/app/schemas/note.py:13` | `_LINK = r"!?\[([^\]]*)\]\([^)]*\)"` квадратичен на строке из `[`; `excerpt` считается для каждого конспекта в `GET /notes` и поиске; тело до 200 000 символов → минуты CPU в event loop | `excerpt("[" * 199_000)` = **66.9 с**; `excerpt("![](" * 50_000)` = 5.3 с | `[^\[\]]*` в классе (линейно) и обрабатывать только начало текста (≈ 20×`limit`) | Низкий: выдержка нормальных конспектов не меняется |
| M-05 | MEDIUM | Безопасность / LLM | `backend/app/api/ai.py:80-84,134-145,158-164`, `backend/app/services/ai_parse.py:87-93` | Нет квоты/лимита на ИИ-джобы: каждая — до 4 вызовов (2 попытки × основной+запасной), до 6000 символов ввода и 2048 токенов ответа; запасной провайдер платный; очередь FIFO одна на всех | Код: `jobs.enqueue` без проверок числа ожидающих | Не больше N ожидающих ИИ-джоб на пользователя (429), дневная квота, дедуп по (вид, объект) | Низкий |
| M-06 | MEDIUM | Надёжность / идемпотентность | `backend/app/services/replan.py:1027-1050` (+ `_get` `:946`) | `apply` проверяет `status == proposed` без блокировки строки → два параллельных применения выполняют операции дважды (операции `add` безусловны) | Пробник: 2 параллельных `apply` одной ревизии → `['ok','ok']`, **2 одинаковых блока** | `SELECT … FOR UPDATE` ревизии в `apply` (или атомарный `UPDATE … WHERE status='proposed' RETURNING`) | Низкий |
| M-07 | MEDIUM | Надёжность / идемпотентность | `backend/app/services/reminder_actions.py:108,180-194`; `backend/app/bot/ai.py:372,432` | Одноразовость кнопок напоминаний (`action_used_at`) и флаги `created`/`applied` у ИИ-карточек проверяются без блокировки → двойное нажатие выполняет действие дважды | Пробник: 2 параллельных «+15 мин» по одному токену → `[200, 200]`, **2 отложенных напоминания** | `with_for_update()` на `Reminder`/`Job` перед проверкой, либо условный `UPDATE … WHERE action_used_at IS NULL` | Низкий |
| M-08 | MEDIUM | Надёжность | `backend/app/services/digest.py:231-291`, `backend/app/notify/message.py:70-75` | Длина сообщений не ограничивается: Telegram — 4096 символов (иначе `TelegramBadRequest`: `/week` молча не отвечает, напоминание уходит в 5 ретраев → failed); Web Push — ~4 КБ полезной нагрузки | Пробник: 70 блоков с названием в 49 символов → `/week` = **4502** символа | Обрезать секции («…и ещё N»), жёсткий потолок ~4000 символов для Telegram и ~3 КБ для тела пуша | Низкий |
| M-09 | MEDIUM | Надёжность / валидация | `backend/app/schemas/schedule.py:24-42`, `backend/app/domain/recurrence.py:168-175`, `backend/app/schemas/event.py:20-34`, `backend/app/schemas/task.py:64-74` | Нет верхних границ дат/длительностей: семестр до 9999 г. → `OverflowError` (500) или материализация сотен тысяч пар одним запросом; событие/блок произвольной длины | `SemesterCreate(classes_end=9999-12-31)` проходит валидацию → `expand_class_rule` падает `OverflowError: date value out of range`; при `9999-12-01` — **416 019** вхождений на одно правило | Семестр ≤ ~1 года, даты в разумном окне (2000–2100), событие ≤ 24 ч (или 7 дней) | Средне-низкий: проверить, что существующие данные укладываются |
| M-10 | MEDIUM | Инфраструктура / зависимости | `backend/Dockerfile:2,4`, `infra/caddy/Dockerfile:2,9`, `infra/backup/Dockerfile:2`, `docker-compose.prod.yml:36`, `infra/deploy.sh:25` | Базовые образы по плавающим тегам и **никогда не перекачиваются** (`up -d --build` без `--pull`); `uv` остаётся в рантайм-образе | trivy: backend — 94 HIGH/CRIT ОС-пакетов (3 CRITICAL `perl-base`, 50 с готовым фиксом, вкл. `openssl`/`libssl3`); локальный `python:3.12-slim` от 2026-06-24; `caddy:2-alpine` — 40 HIGH | Фиксировать образы по digest + Renovate/Dependabot; `build --pull` в деплое; multi-stage для бэкенда; trivy в CI | Низкий; пересборка образов |
| M-11 | MEDIUM | Тесты | `frontend/` | У фронтенда (≈34 тыс. строк, offline-логика, SW, черновики разбивки) нет ни одного теста | `package.json` без test-скрипта и тест-раннера | Vitest для `lib/`, `features/*/{draft,timeline,rrule,windows}.ts`, Playwright-смоук основного сценария | Низкий |
| M-12 | MEDIUM | DX / CI | `.github/workflows/ci.yml` | CI не проверяет типы (mypy), не делает security-сканов (pip-audit/npm audit/trivy/gitleaks), не собирает Docker-образы, не меряет покрытие | Содержимое workflow | Добавить джобы typecheck, security, docker build, coverage с порогом | Низкий |
| L-01 | LOW | Надёжность / CPU | `backend/app/domain/recurrence.py:202-233` | «Невозможные» RRULE (`FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30`) проходят валидацию; dateutil перебирает дни до 9999 г. → ~1.4 с в event loop на каждое разворачивание | Замер `rrule_dates`: 1.41 с (DAILY), 0.43 с (WEEKLY) | При валидации (в потоке) требовать хотя бы одно вхождение; разворачивание — в потоке | Низкий |
| L-02 | LOW | Надёжность | `backend/app/services/study_limits.py:27-33`, `backend/app/core/exceptions.py:72-73` | check-then-insert без `ON CONFLICT` → параллельные PUT дают `IntegrityError` → 500; глобального обработчика `IntegrityError` нет | Пробник: 40 параллельных PUT `/plan/day-limits/{day}` → **19 × 500** | `INSERT … ON CONFLICT DO UPDATE`; обработчик `IntegrityError` → 409 | Низкий |
| L-03 | LOW | Надёжность | `backend/app/services/replan.py:1205`, `backend/app/services/reminders.py:296`, `backend/app/services/schedule_sync.py:430`, `backend/app/services/recurring_tasks.py:95` | Ночные/ежечасные циклы по всем пользователям в одной сессии: ошибка одного пользователя прерывает обработку остальных | Код: нет per-user try/except | Изолировать каждого пользователя (try/except + rollback + лог) | Низкий |
| L-04 | LOW | Надёжность / LLM | `backend/app/ai/provider.py:213,334,406` | Постоянные ошибки API (401/403/404 — неверный ключ или модель) считаются «ИИ недоступен» → запросы молча ждут до 72 ч; `IndexError`/`TypeError` на кривом ответе не ловятся | Код: `httpx.HTTPStatusError` ⊂ `httpx.HTTPError`; `data["choices"][0]` | 4xx (кроме 408/429) → немедленная ошибка + лог конфигурации; ловить `IndexError`, `TypeError` | Низкий |
| L-05 | LOW | Надёжность | `backend/app/services/jobs.py:175-204` | Джоба в `running` с истёкшей арендой забирается снова без проверки `attempts >= max_attempts` → джоба, роняющая воркер (OOM), крутится бесконечно | Код `_claim` | При захвате `running`-джобы с исчерпанными попытками — `failed` | Низкий |
| L-06 | LOW | Надёжность / ресурсы | `backend/app/services/ai_parse.py:43,151-169` | Распознавание фото читает до 4 вложений по 100 МБ целиком в память и кодирует в base64 | Код | Пропускать/уменьшать изображения > ~10 МБ | Низкий |
| L-07 | LOW | Безопасность / заголовки | `infra/caddy/Caddyfile:10-15` | Нет `Content-Security-Policy`, `frame-ancestors`/`X-Frame-Options`, `Permissions-Policy` (кликджекинг частично гасит SameSite=Lax) | Конфиг Caddy | Добавить CSP (`default-src 'self'`, `img-src 'self' data: blob:`, `frame-ancestors 'none'` …) и Permissions-Policy | Средний: CSP может сломать инлайн-стили — проверить в браузере |
| L-08 | LOW | Безопасность / секреты | `backend/app/core/config.py:124-134` | `DATABASE_URL` — `computed_field`: пароль БД в открытом виде попадает в `repr(settings)` и `model_dump()` вопреки `SecretStr` | `repr(Settings())` содержит пароль: `True` | Обычный `@property` (не computed) или `repr=False` + исключение из дампа | Низкий |
| L-09 | LOW | Безопасность / конфиг | `backend/app/core/config.py:118-122` | В проде проверяется только `SECRET_KEY != DEV_SECRET`, длина/энтропия — нет | Код | Требовать ≥ 32 символов в проде | Низкий |
| L-10 | LOW | Безопасность / сессии | `backend/app/services/users.py:61-64`, `backend/app/services/auth.py` | Смена пароля (CLI) не отзывает сессии; просроченные сессии никогда не удаляются; нет «выйти везде» | Код | Отзывать сессии при `set_password`; чистить истёкшие в ночной джобе | Низкий |
| L-11 | LOW | Инфраструктура | `infra/caddy/Dockerfile:9`, `infra/backup/Dockerfile:2-7` | Контейнеры `web` и `backup` работают от root | trivy AVD-DS-0002, semgrep `missing-user-entrypoint` | Caddy — non-root + `CAP_NET_BIND_SERVICE`; backup — дамп от `BACKUP_UID`, root только для `chown` | Средне-низкий |
| L-12 | LOW | Зависимости (фронт) | `frontend/package.json` | В бандл попадает `katex` 0.16.47 (через `rehype-katex`/`remark-math`, CVE-2026-103923 / GHSA-238p-pmpm-9mq7), при этом CSS — от 0.19.0; CLI `shadcn` (цепочка braces CVE-2026-93687) лежит в `dependencies` | `npm ls katex`, npm audit, trivy fs | `overrides: { katex: "^0.19.0" }`; `shadcn` → `devDependencies` | Низкий: проверить рендер формул |
| L-13 | LOW | Валидация | `backend/app/schemas/event.py:27,45,87,114`, `backend/app/schemas/user.py:10`, `backend/app/schemas/settings.py:59` | Нет `max_length` у заметок событий/повторов, пароля логина, списка каналов в настройках | Код | Добавить ограничения | Низкий |
| L-14 | LOW | API | `backend/app/core/exceptions.py:18-20,72-73` | Ошибки валидации — формат FastAPI `{"detail": [...]}`, доменные — `{"error": {code, message}}`; в OpenAPI нет 413/422/429/500 | `POST /api/v1/auth/login {}` → 422 `detail` | Обработчики `RequestValidationError` и 500 в единый формат; дополнить `ERROR_RESPONSES` | Низкий: `frontend/src/lib/errors.ts` уже разбирает оба формата; меняется контракт API и `schema.d.ts` |
| L-15 | LOW | Качество / типы | `backend/app/services/base.py:29`, `backend/app/services/reminder_actions.py:144,151`, `backend/app/services/breakdown.py:304,319`, `backend/app/domain/quickparse.py:384,430,499-503` | mypy `--strict` — 95 ошибок (корень — тип `select()` базового репозитория, переиспользование переменных); стиль-замечания ruff (SIM/N/PT) | Вывод mypy и ruff | Исправить типизацию репозитория, развести переменные, включить mypy в CI поэтапно | Низкий |
| L-16 | LOW | Качество | 20 мест, напр. `backend/app/services/free.py:215,219,230`, `backend/app/api/plan.py:66`, `backend/app/bot/middleware.py:32` | `assert` как рантайм-проверки инвариантов (исчезают при `python -O`) | ruff S101 / bandit B101 | Явные проверки с исключением | Низкий |
| L-17 | LOW | Качество / зависимости | `backend/app/services/ai_parse.py:260-265`, `backend/app/services/breakdown.py:451`, `backend/app/services/users.py:17`, `backend/pyproject.toml` | Мёртвый код (`handle_parse_job`, `handle_photo_job`, `handle_breakdown_job`, `get_user` — 0 ссылок); прямые импорты `starlette`, `anyio`, `cryptography` без объявления зависимостей | vulture, deptry, grep | Удалить мёртвый код; объявить зависимости | Низкий |
| L-18 | LOW | Документация | `README.md:3,42` | README ссылается на `Docs/*.md`, которых нет в репозитории; нет описания архитектуры, конфигурации, тестов; нет `CHANGELOG.md`, pre-commit | Ссылки 404 на GitHub | README уровня портфолио (Фаза 4), `CHANGELOG.md`, `.pre-commit-config.yaml` | Низкий |
| L-19 | LOW | Инфраструктура | `docker-compose.prod.yml:58-67`, `backend/app/worker/__main__.py:170-207` | У `worker` и `bot` нет healthcheck (зависание не заметит никто); SIGTERM не обрабатывается (восстановление держится на арендах) | Конфиг, trivy AVD-DS-0026 | Heartbeat-файл/таблица + healthcheck; обработчик SIGTERM | Низкий |
| L-20 | LOW | Конфигурация | `backend/app/core/config.py:31,52,77-81` | Нет fail-fast для `DEFAULT_TIMEZONE`, формата `APP_URL`, `LLM_FALLBACK_PROVIDER` без URL/модели — ошибки всплывут в рантайме (или джобы будут молча ждать) | Код | Валидаторы в `Settings` | Низкий |
| L-21 | LOW | Тесты | `backend/pyproject.toml` | Нет конфигурации coverage: без `concurrency = greenlet` цифры занижены (82 % vs 90 %); слабо покрыты `worker/__main__.py` 40 %, `bot/review.py` 61 %, `services/notify_render.py` 69 %, `domain/planner/check.py` 77 % | `pytest --cov` с/без greenlet | `[tool.coverage]` с greenlet, тесты на воркер-цикл и рендер напоминаний | Низкий |
| L-22 | LOW | API | `backend/app/api/ai.py:174-177`, `backend/app/services/project_ai.py:161-164` | `dismiss` игнорирует `project_id` и отвечает 204 на чужие/несуществующие id (утечки нет — запрос ограничен `user_id`) | Пробник: B → 204, состояние A не изменилось | Проверять проект и джобу, 404 при несовпадении | Низкий |
| I-01 | INFO | Инфраструктура | `backend/Dockerfile:25` | `--forwarded-allow-ips "*"` безопасно только пока порт api не опубликован | — | Ограничить подсетью compose | — |
| I-02 | INFO | Приватность | `backend/app/ai/prompts.py:31-34` | В промпт зашиты персональные данные (вуз, факультет, курс) — для публичного портфолио | — | Вынести в настройки пользователя | — |
| I-03 | INFO | Приватность | `backend/app/core/config.py:87`, `infra/backup/backup.sh` | `ai_log` хранит полные тексты запросов/ответов 90 дней; бэкапы не шифруются | — | Шифровать бэкапы (age/gpg), сократить срок/маскировать | — |
| I-04 | INFO | Логи | `backend/app/services/attachments.py:71-77` | Подписанные ссылки (`sig`, живут 60 мин) попадают в access-лог uvicorn | — | Не логировать query у `/files` | — |
| I-05 | INFO | CI | `.github/workflows/ci.yml:38-68` | Actions по тегам, не по SHA; нет блока `permissions:` | — | Пин по SHA, `permissions: contents: read` | — |
| I-06 | INFO | Производительность | `backend/Dockerfile:25`, `backend/app/ai/provider.py:298`, списковые эндпоинты | Один процесс uvicorn + CPU-работа в event loop (снапшот планировщика, разбор); новый `httpx.AsyncClient` на каждый вызов LLM; нет пагинации (для одного пользователя приемлемо) | — | `--workers 2`, общий клиент, пагинация по мере роста | — |
| I-07 | INFO | Логика | `backend/app/services/reminder_actions.py:117-146` | Неподходящее действие (напр. `accept` на дедлайне) молча трактуется как «на завтра» | — | 409 на неподдерживаемое действие | — |
| I-08 | INFO | Безопасность (ПОДОЗРЕНИЕ) | `frontend/src/pages/LoginPage.tsx:8-9` | `safeNext` пропускает `/\evil.com`; в SPA это `pushState` на чужой origin (ожидаемо исключение, а не редирект) — в браузере не проверено | — | Разрешать только `^/[^/\\]` | — |
| I-09 | INFO | LLM | `backend/app/services/ai_parse.py:217-233` | Распознавание фото без подтверждения дописывает описание и заполняет пустые название/срок/предмет — prompt injection с фото чужого текста может подставить срок (только в своё задание) | — | Показать изменения карточкой с «Отменить» | — |
| I-10 | INFO | Время | `backend/app/worker/__main__.py:44,60-67` | Ночная задача — в 03:00 `DEFAULT_TIMEZONE` для всех пользователей | — | Для мультипользовательского режима — по TZ пользователя | — |

## Не проверено и почему

- Фронтенд в браузере (UI-сценарии, service worker, офлайн, share-target) — нет e2e-прогона; проверены только статически (oxlint, tsc, ручное чтение).
- Реальные внешние сервисы: Telegram Bot API, FCM/APNs/Mozilla push (поведение при payload > 4 КБ — по документированным лимитам), Ollama/облачный LLM.
- Прод-окружение: сервер, ufw, SSH-туннель, Docker daemon, содержимое `.env`/`.env.prod` (сознательно не читались); образ `veillou-web` не собирался — просканирован базовый `caddy:2-alpine` из локального кэша.
- `semgrep --config auto` — заменён явными наборами правил без отправки метрик.
- Нагрузочные сценарии M-01 (реальное исчерпание памяти) не воспроизводились — доказательство на уровне кода FastAPI.
- Корректность планировщика CP-SAT и builder'а напоминаний независимо не аудировалась — опора на существующие тесты, включая property-based.
- mypy только для `app/` и `scripts/`; из 95 ошибок вручную разобрано ≈ 15.
- Downgrade миграций проверен только на пустой БД (без данных).
- Доступность (a11y), лицензии зависимостей, производительность фронтенда.
- I-08 — гипотеза, в браузере не проверена.

## Что я мог пропустить (второй проход)

После первого прохода повторно прошёл: время/таймзоны (grep naive-вызовов), голые `except`,
регулярки на длинном вводе (нашёл M-04), гонки check-then-act (нашёл M-06, M-07, L-02),
лимиты внешних каналов (нашёл M-08), границы дат (нашёл M-09), утечку секретов через
`repr` (нашёл L-08), запуск с нуля на чистом клоне (нашёл H-02). Дальнейшие кандидаты для
углубления в Фазе 3: остальные места вида «select → проверка → insert» без `ON CONFLICT`
и границы входных данных в `services/exams.py`, `services/backlog.py`, `services/projects.py`.

---

**Остановка по регламенту.** Фиксы (Фаза 3: CRITICAL → HIGH → MEDIUM → LOW, тест → фикс → зелёный
прогон → атомарный коммит с ID) начну после подтверждения.

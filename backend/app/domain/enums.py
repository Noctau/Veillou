"""Перечисления предметной области. Общие для domain, моделей и API-схем."""

from enum import StrEnum


class EventKind(StrEnum):
    """Поведение события в планировщике (смысл задаёт тип занятости, Part 2 M17.1)."""

    busy = "busy"  # жёсткое: занятость (тип занятости — `event_type_id`)
    subtask = "subtask"  # шаг задачи (гибкое)
    backlog = "backlog"  # дело из ящика (гибкое)
    prep = "prep"  # подготовка к событию (гибкое)
    project = "project"  # работа над проектом — резерв недельной нормы (гибкое)


class EventStatus(StrEnum):
    planned = "planned"
    done = "done"
    cancelled = "cancelled"
    missed = "missed"


class TemplateType(StrEnum):
    """Откуда материализовано вхождение."""

    schedule_rule = "schedule_rule"


class PatternKind(StrEnum):
    """Паттерн правила расписания (domain/recurrence.py)."""

    weekly = "weekly"  # по дням недели, с маской недель цикла периода
    day_cycle = "day_cycle"  # смены: N дней через M от якорной даты
    rrule = "rrule"
    once = "once"


class DayRuleKind(StrEnum):
    """Правило назначения режима дня (domain/dayprofile.py). Приоритет: dates >
    event_day / day_after (по позиции) > weekdays > первый режим."""

    dates = "dates"  # конкретные даты: «завтра — выходной», «отпуск 1–14 августа»
    event_day = "event_day"  # в день, когда начинается событие типа
    day_after = "day_after"  # на следующий день после начала события типа («после ночной»)
    weekdays = "weekdays"  # по дням недели


# ---------- справочники (M4.1) ----------


class CategoryKey(StrEnum):
    """Системные категории (ТЗ §4.8). Пользовательские категории — без ключа."""

    study = "study"
    work = "work"
    home = "home"
    personal = "personal"


class ActionTypeKey(StrEnum):
    """Тип действия — когда дело уместно делать. Набор фиксированный, окна правятся."""

    people = "people"  # связь с людьми
    institutions = "institutions"  # учреждения
    study = "study"  # самостоятельная учёба
    outside = "outside"  # вне дома
    home = "home"  # домашние дела
    personal = "personal"  # личное


class CategoryIcon(StrEnum):
    """Иконки категорий (имена lucide-react в kebab-case)."""

    graduation_cap = "graduation-cap"
    briefcase = "briefcase"
    house = "house"
    heart = "heart"
    shopping_cart = "shopping-cart"
    stethoscope = "stethoscope"
    file_text = "file-text"
    dumbbell = "dumbbell"
    users = "users"
    plane = "plane"
    star = "star"
    tag = "tag"
    pencil = "pencil"
    presentation = "presentation"
    flask_conical = "flask-conical"
    book_open = "book-open"
    clipboard_check = "clipboard-check"
    user = "user"
    coffee = "coffee"
    calendar = "calendar"
    clock = "clock"


# ---------- сферы и поля (Part 2, M16) ----------


class FieldType(StrEnum):
    """Тип пользовательского поля (domain/fields.py)."""

    text = "text"
    number = "number"
    bool = "bool"
    select = "select"  # один из списка
    multiselect = "multiselect"  # несколько из списка
    date = "date"
    contact = "contact"  # имя, роль, телефон, email, ссылка
    link = "link"
    area_ref = "area_ref"  # ссылка на другую сферу


class AreaSection(StrEnum):
    """Разделы страницы сферы."""

    schedule = "schedule"
    tasks = "tasks"
    notes = "notes"
    materials = "materials"
    prep = "prep"
    projects = "projects"


# ---------- задания (M4.2) ----------


class TaskTypeKey(StrEnum):
    """Ключи типов задач из Part 1: только для сида справочника `task_types` (миграция)
    и словаря быстрого ввода (`quickparse`, до M21.1). Логику по ним не ветвить."""

    homework = "homework"  # ДЗ
    report = "report"  # доклад
    essay = "essay"  # реферат
    lab = "lab"  # лабораторная
    coursework = "coursework"  # курсовая
    reading = "reading"  # чтение
    exam_prep = "exam_prep"  # подготовка к экзамену
    other = "other"


class Priority(StrEnum):
    normal = "normal"
    high = "high"


class TaskStatus(StrEnum):
    active = "active"
    done = "done"
    cancelled = "cancelled"
    # Предложение автозадачи с подтверждением: не планируется, ждёт вечернего разбора
    proposed = "proposed"


class EventRuleWhen(StrEnum):
    """Автозадача (M19): до или после вхождения события."""

    before = "before"  # закончить за N минут до начала
    after = "after"  # не раньше конца; не позже чем через N дней / до следующего вхождения


class SubtaskStatus(StrEnum):
    todo = "todo"
    done = "done"


class Feel(StrEnum):
    """Как прошло по сравнению с оценкой — для калибровки (M9.4)."""

    faster = "faster"
    ok = "ok"
    slower = "slower"


class SourceType(StrEnum):
    """Сущность-источник гибкого блока в `events`."""

    subtask = "subtask"
    task = "task"  # задание без подзадач — одним блоком
    backlog_item = "backlog_item"
    exam_session = "exam_session"  # день подготовки к экзамену (M12)
    exam = "exam"  # жёсткое событие самого экзамена
    project = "project"  # резерв недельной нормы проекта (M13.1)


# ---------- долгий ящик (M4.6) ----------


class BacklogStatus(StrEnum):
    active = "active"
    done = "done"
    archived = "archived"  # «неактуально»


class BacklogCondition(StrEnum):
    """Условия дела — фиксированный набор чипов, без свободного текста."""

    weekday_daytime = "weekday_daytime"  # только в будни днём
    needs_laptop = "needs_laptop"  # нужен ноутбук
    # «В часы работы учреждений» — теперь `BacklogItem.hours_action_type_id` (M15.2),
    # «в дни пар» — `BacklogItem.days_event_type_id` (в дни событий типа, M17.5)


# ---------- файлы (M5.1) ----------


class AttachmentOwner(StrEnum):
    """К чему приложен файл."""

    task = "task"
    project = "project"
    note = "note"  # страницы фото-конспекта, PDF
    source = "source"  # файл источника литературы


# ---------- конспекты (M5.2) ----------


class NoteKind(StrEnum):
    """Чем в основном является конспект — от этого зависит экран просмотра."""

    text = "text"  # Markdown + формулы
    photo = "photo"  # фото страниц тетради
    file = "file"  # PDF и другие файлы
    link = "link"  # ссылка на Диск / сайт


# ---------- литература (M5.5) ----------


class SourceKind(StrEnum):
    textbook = "textbook"  # учебник, книга
    article = "article"  # статья
    website = "website"  # сайт
    other = "other"


class SourceStatus(StrEnum):
    to_read = "to_read"
    reading = "reading"
    done = "done"


# ---------- проекты (M4.7) ----------


class ProjectStatus(StrEnum):
    active = "active"
    done = "done"
    archived = "archived"


class MilestoneStatus(StrEnum):
    planned = "planned"
    done = "done"


# ---------- уведомления (M6) ----------


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class JobKind(StrEnum):
    reminders_sync = "reminders.sync"  # пересобрать будущие напоминания пользователя
    plan_preview = "plan.preview"  # пересчитать превью плана после правок
    ai_breakdown = "ai.breakdown"  # разбить задание на шаги (черновик)
    ai_parse = "ai.parse"  # разобрать свободный текст (бот, ＋)
    ai_photo = "ai.photo"  # распознать фото задания
    ai_milestones = "ai.milestones"  # предложить этапы проекта (черновик)
    event_tasks_sync = "event_tasks.sync"  # автозадачи от событий и сроки «к следующему»


# ИИ-джобы идут своей очередью: по одной, по порядку постановки, и ждут, если ИИ недоступен
AI_JOB_KINDS = frozenset(
    {JobKind.ai_breakdown, JobKind.ai_parse, JobKind.ai_photo, JobKind.ai_milestones}
)


class ReminderKind(StrEnum):
    morning_digest = "morning_digest"
    before_event = "before_event"  # перед событием типа с `remind_before_min`
    deadline = "deadline"
    subtask_start = "subtask_start"
    evening_review = "evening_review"
    weekly_review = "weekly_review"
    test = "test"  # «Проверить уведомления» из Настроек


class ReminderStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    skipped = "skipped"  # устарело (событие отменено, задание сделано, истёк срок)
    failed = "failed"  # кончились попытки


class ReminderAction(StrEnum):
    """Кнопки на напоминании (Telegram и Android-пуш)."""

    done = "done"  # «Сделано»
    snooze = "snooze"  # «+15 мин»
    tomorrow = "tomorrow"  # «На завтра»
    reschedule = "reschedule"  # вечерний разбор: «Перенести всё»
    pick = "pick"  # вечерний разбор: «По одному» (только Telegram)
    accept = "accept"  # недельный разбор: «Взять на неделю»


# ---------- перепланирование (M9) ----------


class PlanRevisionStatus(StrEnum):
    proposed = "proposed"  # превью ждёт «Применить / Отменить»
    applied = "applied"
    undone = "undone"  # применили и откатили
    dismissed = "dismissed"  # превью отклонено
    superseded = "superseded"  # превью устарело: есть новое


class PlanReason(StrEnum):
    """Почему пересчитали план."""

    manual = "manual"  # кнопка «Перепланировать»
    changes = "changes"  # задания, расписание, настройки
    missed = "missed"  # «не сделано»
    nightly = "nightly"  # ночная джоба: прошедшее неотмеченное → missed
    weekly = "weekly"  # недельный разбор: дела из ящика на неделю
    exam = "exam"  # план подготовки к экзамену


# ---------- ИИ (M10) ----------


class AIPurpose(StrEnum):
    """Зачем звали ИИ — колонка `ai_log.purpose`."""

    breakdown = "breakdown"
    parse = "parse"
    photo = "photo"
    milestones = "milestones"


class AIOrigin(StrEnum):
    """Откуда запрос к ИИ — куда отдавать результат."""

    app = "app"  # фронт поллит GET /jobs/{id}
    telegram = "telegram"  # воркер сам отвечает в чат


# ---------- экзамены (M12) ----------


class ExamQuestionStatus(StrEnum):
    not_started = "not_started"
    learned = "learned"
    review = "review"  # «повторить»: вопрос возвращается в цикл повторений


class ExamSessionKind(StrEnum):
    learn = "learn"  # выучить новые вопросы
    review = "review"  # повторить (+1 / +3 / +7 дней)
    run = "run"  # общий прогон накануне экзамена


class ExamSessionStatus(StrEnum):
    planned = "planned"
    done = "done"
    missed = "missed"

"""Промпты. Чистые функции: контекст (dataclass) → сообщения.

Схема ответа уходит провайдеру отдельно (structured outputs), но поля и
правила всё равно перечислены в тексте — маленькие локальные модели так
заметно реже путают смысл полей.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.ai.provider import Message
from app.domain.breakdown import MAX_STEP_MIN, MIN_STEP_MIN, fmt_minutes

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]

ROLE = "Ты — помощник-планировщик. Пишешь по-русски, коротко и по делу."
ABOUT_LIMIT = 1000


@dataclass(frozen=True)
class Hint:
    """Строка справочника пользователя для промпта: название (значение в ответе) и
    подсказки — синонимы или описание."""

    name: str
    synonyms: Sequence[str] = ()


# Совместимость: тип задачи — та же подсказка
TaskTypeHint = Hint


@dataclass(frozen=True)
class AreaHint:
    """Сфера пользователя: название (значение `area` в ответе) и её тип («Предмет»)."""

    name: str
    kind: str = ""
    synonyms: Sequence[str] = ()


@dataclass(frozen=True)
class Profile:
    """Кто пользователь и его справочники — общий контекст всех промптов (M21.2).
    Вместо зашитого описания конкретного человека: «о себе» из настроек и названия
    кирпичей его настройки. Ответы ИИ ограничены этими списками (with_choices)."""

    about: str = ""
    areas: Sequence[AreaHint] = ()
    task_types: Sequence[Hint] = ()
    action_types: Sequence[Hint] = ()
    categories: Sequence[str] = ()

    @property
    def area_names(self) -> list[str]:
        return [a.name for a in self.areas]

    @property
    def task_type_names(self) -> list[str]:
        return [t.name for t in self.task_types]

    @property
    def action_type_names(self) -> list[str]:
        return [t.name for t in self.action_types]


def who(profile: Profile) -> str:
    """Начало системного промпта: роль и «о себе» пользователя."""
    about = " ".join(profile.about.split())[:ABOUT_LIMIT]
    if not about:
        return ROLE
    return f"{ROLE}\n\nО пользователе (с его слов): {about}"


def _hints(items: Sequence[Hint]) -> list[str]:
    return [f"- {t.name}" + (f" ({', '.join(t.synonyms)})" if t.synonyms else "") for t in items]


def task_types_text(types: Sequence[Hint]) -> str:
    """Типы задач из справочника пользователя: task_type — название из списка."""
    if not types:
        return "Типов задач в списке нет — task_type всегда пустая строка."
    return (
        "Типы задач (task_type — одно название из списка, точно как написано; "
        "ни один не подходит — пустая строка):\n" + "\n".join(_hints(types))
    )


def action_types_text(types: Sequence[Hint]) -> str:
    """Типы действий: когда дело уместно делать. В скобках — слова-подсказки."""
    if not types:
        return "Типов действий в списке нет — action_type всегда пустая строка."
    return (
        "Типы действий (action_type — когда это уместно делать; одно название из списка, "
        "точно как написано; ни один не подходит — пустая строка):\n" + "\n".join(_hints(types))
    )


def categories_text(names: Sequence[str]) -> str:
    if not names:
        return "Категорий в списке нет — category всегда пустая строка."
    return "Категории (category — одно название из списка или пустая строка): " + ", ".join(names)


def areas_text(areas: Sequence[AreaHint]) -> str:
    """Сферы пользователя: предметы, ученики, клиенты, проекты работы — что есть."""
    if not areas:
        return "Сфер в списке нет — area всегда пустая строка."
    lines = []
    for a in areas:
        extra = [a.kind] if a.kind else []
        extra += list(a.synonyms)
        lines.append(f"- {a.name}" + (f" ({', '.join(extra)})" if extra else ""))
    return (
        "Сферы пользователя (area — одно название из списка, точно как написано, "
        "или пустая строка):\n" + "\n".join(lines)
    )


def fmt_date(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]} {d.year}"


def fmt_deadline(deadline: datetime, today: date) -> str:
    days = (deadline.date() - today).days
    when = f"{fmt_date(deadline.date())}, {deadline:%H:%M}"
    if days < 0:
        return f"{when} (уже прошёл)"
    if days == 0:
        return f"{when} (сегодня)"
    return f"{when} (через {days} дн.)"


def _block(text: str) -> str:
    return '"""\n' + text.strip() + '\n"""'


# ---------- разбивка ----------


@dataclass(frozen=True)
class PrevStep:
    title: str
    estimate_min: int


@dataclass(frozen=True)
class BreakdownContext:
    title: str
    today: date
    task_type: str | None = None  # название типа задачи, если задан
    description: str = ""
    area: str | None = None  # «Климатология (Предмет)»
    project: str | None = None
    # Настенное время в TZ пользователя
    deadline: datetime | None = None
    # Сколько свободно до дедлайна в «её» минутах (уже с учётом калибровки)
    free_minutes: int | None = None
    done_steps: Sequence[str] = ()
    # Перегенерация: прошлый вариант и комментарий
    previous: Sequence[PrevStep] = ()
    comment: str | None = None
    profile: Profile = Profile()


BREAKDOWN_RULES = f"""Задача: разбить задание на конкретные шаги для планировщика.

Правила:
1. Каждый шаг — одно действие, которое можно сделать за один подход: {MIN_STEP_MIN}–{MAX_STEP_MIN} минут.
   Большую работу дели на несколько шагов («написать раздел 1», «написать раздел 2»), а не на один длинный.
2. Название шага начинается с глагола и понятно без контекста: «Найти 3 источника по теме», а не «Источники».
3. Шагов обычно 3–8; для большой работы — до 15. Однотипные мелочи объединяй:
   «Решить задачи 3.1–3.4», а не по шагу на задачу; «сфотографировать и отправить» — один шаг.
4. Оценки реалистичные для этого человека; total_estimate_min — сумма оценок шагов.
5. depends_on — номера шагов (order), без которых этот шаг начать нельзя. Только прямые зависимости:
   если 3 зависит от 2, а 2 от 1, у шага 3 пиши только [2].
6. action_type задаётся у каждого шага: что-то спросить, согласовать или написать человеку — тип
   для связи с людьми; работа над текстом, расчёты, чтение — тип для сосредоточенной работы
   (по названиям и подсказкам из списка).
7. Не добавляй шаги, которые уже сделаны.
8. note — короткая подсказка к шагу (что взять, на что обратить внимание) или пустая строка.
9. warning — только если задание непонятно без уточнений (нет темы, объёма, неясно, что сдавать): коротко, что уточнить.
   Про нехватку времени не пиши — это посчитают отдельно. Иначе null.
10. task_type и category — для всего задания.

{{action_types}}

{{task_types}}

{{categories}}

Ответ — только JSON:
{{"task_type": "...", "category": "...", "subtasks": [{{"order": 1, "title": "...", "estimate_min": 60,
"action_type": "...", "depends_on": [], "note": ""}}], "total_estimate_min": 60, "warning": null}}"""


def breakdown_messages(ctx: BreakdownContext) -> list[Message]:
    lines = [f"Задание: {ctx.title}"]
    if ctx.task_type:
        lines.append(f"Тип задания: {ctx.task_type}")
    if ctx.area:
        lines.append(f"Сфера: {ctx.area}")
    if ctx.project:
        lines.append(f"Проект: {ctx.project}")
    lines.append(f"Сегодня: {fmt_date(ctx.today)}")
    if ctx.deadline is not None:
        lines.append(f"Дедлайн: {fmt_deadline(ctx.deadline, ctx.today)}")
    else:
        lines.append("Дедлайн: не задан")
    if ctx.free_minutes is not None:
        lines.append(
            f"Свободного времени до дедлайна: около {fmt_minutes(ctx.free_minutes)} (для ориентира)"
        )
    if ctx.description.strip():
        lines.append(f"Описание задания:\n{_block(ctx.description[:6000])}")
    if ctx.done_steps:
        lines.append("Уже сделано:\n" + "\n".join(f"- {s}" for s in ctx.done_steps))
    rules = (
        BREAKDOWN_RULES.replace("{action_types}", action_types_text(ctx.profile.action_types))
        .replace("{task_types}", task_types_text(ctx.profile.task_types))
        .replace("{categories}", categories_text(ctx.profile.categories))
    )
    messages = [
        Message("system", f"{who(ctx.profile)}\n\n{rules}"),
        Message("user", "\n".join(lines)),
    ]
    if ctx.previous or ctx.comment:
        prev = "\n".join(
            f"{i}. {s.title} — {s.estimate_min} мин" for i, s in enumerate(ctx.previous, 1)
        )
        redo = ["Прошлый вариант разбивки:", prev] if prev else []
        if ctx.comment:
            redo.append(f"Комментарий пользователя: «{ctx.comment.strip()}»")
        redo.append("Сделай новую разбивку с учётом комментария.")
        messages.append(Message("user", "\n".join(redo)))
    return messages


# ---------- разбор свободного текста ----------


@dataclass(frozen=True)
class ParseContext:
    text: str
    now: datetime  # настенное время пользователя
    profile: Profile = Profile()


DATE_RULES = """Даты (смотри календарь ниже):
- deadline_date — день срока ГГГГ-ММ-ДД: «к пятнице» — ближайшая пятница после сегодня,
  «к следующей пятнице» — пятница следующей недели, «через неделю» — сегодня + 7 дней,
  «до 15 октября» — ближайшее 15 октября в будущем.
- deadline_time — ЧЧ:ММ, только если время названо явно («к 10:00», «в 15»), иначе пустая строка.
- Нет срока — пустые строки. Не выдумывай срок."""


def calendar(today: date, days: int = 21) -> str:
    """«чт 08.10 — сегодня, пт 09.10, …» — модели плохо считают дни недели сами."""
    short = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    items = []
    for i in range(days):
        d = today + timedelta(days=i)
        label = f"{short[d.weekday()]} {d.isoformat()}"
        items.append(f"{label} (сегодня)" if i == 0 else label)
    weeks = [", ".join(items[i : i + 7]) for i in range(0, len(items), 7)]
    return "Календарь:\n" + "\n".join(weeks)


def parse_messages(ctx: ParseContext) -> list[Message]:
    p = ctx.profile
    system = f"""{who(p)}

Задача: по сообщению пользователя понять, что это, и заполнить карточку.

kind:
- task — задача с результатом (сделать, сдать, подготовить, прочитать, написать), обычно со сроком;
- backlog — бытовое или личное дело без жёсткого срока («записаться к стоматологу», «купить лампочки»);
- event — встреча или мероприятие с точным временем начала.

title — короткое название, до 80 символов, без даты и лишних слов: «Отчёт о продажах за квартал»,
а не «надо до пятницы сдать отчёт о продажах за квартал».
task_type — тип задачи из списка; для дел и событий — пустая строка.
area — если в сообщении упомянута сфера из списка (в любом падеже, сокращённо, по имени
или по теме), иначе пустая строка.
description — только требования, которые есть в самом сообщении (объём, тема, оформление),
коротко и без даты. Ничего не придумывай и не дописывай от себя. Нет требований — пустая строка.
action_type — когда это уместно делать: название из списка типов действий.

{DATE_RULES}

{task_types_text(p.task_types)}

{action_types_text(p.action_types)}

Ответ — только JSON по схеме."""
    user = "\n".join(
        [
            f"Сегодня: {fmt_date(ctx.now.date())}, сейчас {ctx.now:%H:%M}",
            calendar(ctx.now.date()),
            areas_text(p.areas),
            f"Сообщение:\n{_block(ctx.text[:6000])}",
        ]
    )
    return [Message("system", system), Message("user", user)]


# ---------- фото задания ----------


def photo_messages(ctx: ParseContext) -> list[Message]:
    """Фото доски, листка или экрана с заданием. `ctx.text` — подпись к фото (может быть пустой)."""
    p = ctx.profile
    system = f"""{who(p)}

Задача: на фото — задание (доска, листок, слайд, экран, документ). Перепиши его и заполни карточку.

text — весь текст задания с фото, как написан (формулы — как получится, обычным текстом).
Если текста не видно — пустая строка.
title — короткое название задания, до 80 символов.

area — сфера из списка, если она видна на фото или в подписи, иначе пустая строка.

{DATE_RULES}

{task_types_text(p.task_types)}

Ответ — только JSON по схеме."""
    lines = [
        f"Сегодня: {fmt_date(ctx.now.date())}",
        calendar(ctx.now.date()),
        areas_text(p.areas),
    ]
    if ctx.text.strip():
        lines.append(f"Подпись к фото:\n{_block(ctx.text[:2000])}")
    return [Message("system", system), Message("user", "\n".join(lines))]


# ---------- этапы проекта (M13.2) ----------


@dataclass(frozen=True)
class ExistingMilestone:
    title: str
    date: date | None
    done: bool


@dataclass(frozen=True)
class MilestonesContext:
    title: str
    today: date
    description: str = ""
    deadline: date | None = None
    weekly_norm_min: int | None = None
    existing: Sequence[ExistingMilestone] = ()
    tasks: Sequence[str] = ()
    # Перегенерация: прошлый вариант («название — дата») и комментарий
    previous: Sequence[str] = ()
    comment: str | None = None
    # Паузы и периоды пользователя («Сессия: 2027-01-09 — 2027-01-25»)
    pauses: Sequence[str] = ()
    profile: Profile = Profile()


MILESTONES_RULES = """Задача: предложить этапы (вехи) долгого проекта — от сегодня до итогового срока.

Правила:
1. Этап — проверяемый результат, а не мелкое действие: «Обзор литературы готов», «Глава 2 написана»,
   а не «почитать статью». Обычно 4–8 этапов.
2. Пример для дипломной работы: тема согласована → обзор литературы → данные и методика →
   расчёты и результаты → текст глав → полный текст на проверке у руководителя → предзащита → защита.
   Для других проектов (запуск продукта, ремонт, переезд, поступление, подготовка к соревнованию) —
   свои шаги, по описанию.
3. date — ГГГГ-ММ-ДД, этапы по порядку дат, не раньше сегодняшнего дня и не позже итогового срока.
   Последний этап — сам итог (защита, подача документов) в итоговый срок.
   Оставь запас: полный текст — за 3–4 недели до защиты, предзащита — за 1–3 недели.
4. Срок этапа соразмерен работе: обзор литературы, обработка данных, глава — от 3–4 недель
   каждый; первый крупный этап — не раньше чем через 2–3 недели от сегодня.
5. Учитывай паузы и загруженные периоды пользователя из сообщения (сессия, отпуск, сезон):
   на них большие этапы не ставь. Учитывай общеизвестные сроки, если проект с ними связан
   (приёмные кампании — летом, отчётность — в конце квартала). Этапы распределяй равномерно,
   без пустых месяцев.
6. Этапы, которые уже есть в проекте, не повторяй; новые встраивай в их последовательность по датам.
7. Итогового срока нет — распредели этапы на 3–6 месяцев и попроси в warning указать срок.
8. note — что входит в этап, одной фразой, или пустая строка.
9. warning — коротко, что уточнить, если описания мало для плана; иначе пустая строка.

Ответ — только JSON:
{"milestones": [{"title": "...", "date": "ГГГГ-ММ-ДД", "note": ""}], "warning": ""}"""


def milestones_messages(ctx: MilestonesContext) -> list[Message]:
    lines = [f"Проект: {ctx.title}", f"Сегодня: {fmt_date(ctx.today)}"]
    if ctx.deadline is not None:
        days = (ctx.deadline - ctx.today).days
        lines.append(f"Итоговый срок: {fmt_date(ctx.deadline)} (через {days} дн.)")
    else:
        lines.append("Итоговый срок: не задан")
    if ctx.weekly_norm_min:
        lines.append(f"На проект в неделю: около {fmt_minutes(ctx.weekly_norm_min)}")
    if ctx.description.strip():
        lines.append(f"Описание проекта:\n{_block(ctx.description[:6000])}")
    if ctx.existing:
        items = []
        for m in ctx.existing:
            when = m.date.isoformat() if m.date else "без даты"
            items.append(f"- {m.title} — {when}{' (выполнен)' if m.done else ''}")
        lines.append("Этапы, которые уже есть:\n" + "\n".join(items))
    if ctx.tasks:
        lines.append("Задания проекта:\n" + "\n".join(f"- {t}" for t in ctx.tasks))
    if ctx.pauses:
        lines.append("Паузы и периоды пользователя:\n" + "\n".join(f"- {p}" for p in ctx.pauses))
    messages = [
        Message("system", f"{who(ctx.profile)}\n\n{MILESTONES_RULES}"),
        Message("user", "\n".join(lines)),
    ]
    if ctx.previous or ctx.comment:
        redo = (
            ["Прошлый вариант этапов:", *(f"- {p}" for p in ctx.previous)] if ctx.previous else []
        )
        if ctx.comment:
            redo.append(f"Комментарий пользователя: «{ctx.comment.strip()}»")
        redo.append("Предложи этапы заново с учётом комментария.")
        messages.append(Message("user", "\n".join(redo)))
    return messages


# ---------- ИИ-настройка (M21.4) ----------


@dataclass(frozen=True)
class SetupContext:
    text: str
    today: date
    profile: Profile = Profile()
    # Что уже настроено: раздел → названия («Типы занятости: Смена, Личное»)
    existing: Mapping[str, Sequence[str]] = field(default_factory=dict)
    # Перегенерация: прошлый черновик (кратко) и комментарий
    previous: Sequence[str] = ()
    comment: str | None = None


SETUP_RULES = """Задача: по описанию занятости собрать черновик настройки планировщика из кирпичей.

Кирпичи:
- area_types и areas — сферы: к чему относятся занятия и задачи (место работы, учёба,
  ученик, предмет, клиент, секция). Каждая названная в описании конкретная вещь — сфера в areas
  с названием из описания; её тип — в area_types. Поля типа — только если их назвали.
- event_types — типы жёсткой занятости, в которую дела ставить нельзя. Только те, что есть
  в описании. travel_min — дорога до и после, если о ней сказано; remind_min — за сколько
  напомнить (обычно 30–60; 0 — не надо); is_rest — только для отдыха; show_now_next — для
  основной занятости дня.
- rules — расписание каждого типа занятости:
  pattern weekly — по дням недели, weekdays — названия дней: пн, вт, ср, чт, пт, сб, вс;
  pattern shifts — сменный график «N через M»: «2/2» и «два через два» → on_days 2, off_days 2,
  «сутки через трое» → on_days 1, off_days 3. Сменный график — ВСЕГДА shifts, не weekly.
  anchor — дата первой смены, только если её назвали;
  pattern once — один раз в дату date.
  start и end — ЧЧ:ММ («с 8 до 20» → 08:00 и 20:00); ночная смена — конец раньше начала.
  Если дневные и ночные смены чередуются в одном графике — два правила shifts.
  event_type — название из event_types; area — название сферы из areas (не типа сферы).
- day_profiles — особый распорядок дня, только если о нём сказано: подъём (wake), отбой
  (sleep), когда можно ставить дела (work_start–work_end). Назначается по дням недели
  (weekdays), в дни событий типа (on_event_type) или на следующий день после события
  (after_event_type). Обычные будни и выходные уже настроены — их не добавляй.
- budgets — «не больше N минут в день», только если лимит назван; event_types — какие
  типы занятости в него идут, action_types — какие типы действий из текущей настройки.
- task_types — только типы задач, которые явно названы.
- about — одна-две фразы о человеке своими словами.

Как понимать:
- «по субботам», «каждый вторник и четверг» → weekly, weekdays [сб] или [вт, чт];
- «5/2», «пятидневка», «по будням» → weekly, weekdays [пн, вт, ср, чт, пт];
- «2/2», «два через два» → shifts, on_days 2, off_days 2 — даже если смены дневные и ночные;
- «сутки через трое» → shifts, on_days 1, off_days 3;
- «не больше 3 часов в день на домашку» — это budgets, а не правило расписания;
- учёба или работа без названного времени — сфера (areas), но без правила.

Правила:
1. Только то, что есть в описании. Ничего не придумывай.
2. Если в текущей настройке уже есть подходящий кирпич — используй его название точно.
3. warning — что в описании неясно для расписания; если всё ясно — пустая строка.

Ответ — только JSON по схеме."""

SETUP_SECTIONS = {
    "area_types": "Типы сфер",
    "areas": "Сферы",
    "event_types": "Типы занятости",
    "day_profiles": "Режимы дня",
    "budgets": "Лимиты",
    "task_types": "Типы задач",
    "action_types": "Типы действий",
}


def setup_messages(ctx: SetupContext) -> list[Message]:
    lines = [f"Сегодня: {fmt_date(ctx.today)}", calendar(ctx.today, days=14)]
    existing = [
        f"- {label}: {', '.join(ctx.existing[key])}"
        for key, label in SETUP_SECTIONS.items()
        if ctx.existing.get(key)
    ]
    lines.append(
        "Текущая настройка:\n" + "\n".join(existing) if existing else "Текущая настройка: пусто."
    )
    lines.append(f"Описание:\n{_block(ctx.text[:4000])}")
    messages = [
        Message("system", f"{who(ctx.profile)}\n\n{SETUP_RULES}"),
        Message("user", "\n".join(lines)),
    ]
    if ctx.previous or ctx.comment:
        redo = ["Прошлый черновик:", *(f"- {p}" for p in ctx.previous)] if ctx.previous else []
        if ctx.comment:
            redo.append(f"Комментарий пользователя: «{ctx.comment.strip()}»")
        redo.append("Собери черновик заново с учётом комментария.")
        messages.append(Message("user", "\n".join(redo)))
    return messages

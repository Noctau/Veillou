"""Промпты. Чистые функции: контекст (dataclass) → сообщения.

Схема ответа уходит провайдеру отдельно (structured outputs), но поля и
правила всё равно перечислены в тексте — маленькие локальные модели так
заметно реже путают смысл полей.
"""

from collections.abc import Sequence
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

WHO = (
    "Ты — помощник-планировщик студентки 4 курса бакалавриата (МГУ, географический "
    "факультет, кафедра метеорологии и климатологии). Пишешь по-русски, коротко и по делу."
)

ACTION_TYPES = """Типы действий (action_type):
- study — самостоятельная учёба: чтение, расчёты, анализ данных, написание текста, подготовка;
- people — связь с людьми: написать или спросить преподавателя, научного руководителя, одногруппников;
- institutions — учреждения: библиотека, деканат, кафедра, МФЦ (в часы работы);
- outside — вне дома: съездить, купить, распечатать;
- home — домашние дела;
- personal — личное."""

TASK_TYPES = """Типы заданий (task_type): homework — ДЗ, задачи; report — доклад, презентация;
essay — реферат, эссе; lab — лабораторная, практикум; coursework — курсовая, ВКР, большая работа;
reading — прочитать, законспектировать; exam_prep — подготовка к экзамену или зачёту;
other — всё остальное."""

CATEGORIES = (
    "Категории (category): study — учёба; work — работа (в т. ч. задания с работы для ВКР); "
    "home — быт; personal — личное."
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
    task_type: str | None = None
    description: str = ""
    subject: str | None = None
    project: str | None = None
    # Настенное время в TZ пользователя
    deadline: datetime | None = None
    # Сколько свободно до дедлайна в «её» минутах (уже с учётом калибровки)
    free_minutes: int | None = None
    done_steps: Sequence[str] = ()
    # Перегенерация: прошлый вариант и комментарий
    previous: Sequence[PrevStep] = ()
    comment: str | None = None


BREAKDOWN_RULES = f"""Задача: разбить задание на конкретные шаги для планировщика.

Правила:
1. Каждый шаг — одно действие, которое можно сделать за один подход: {MIN_STEP_MIN}–{MAX_STEP_MIN} минут.
   Большую работу дели на несколько шагов («написать раздел 1», «написать раздел 2»), а не на один длинный.
2. Название шага начинается с глагола и понятно без контекста: «Найти 3 статьи о муссонах», а не «Источники».
3. Шагов обычно 3–8; для курсовой или большого реферата — до 15. Однотипные мелочи объединяй:
   «Решить задачи 3.1–3.4», а не по шагу на задачу; «сфотографировать и отправить» — один шаг.
4. Оценки реалистичные для студентки; total_estimate_min — сумма оценок шагов.
5. depends_on — номера шагов (order), без которых этот шаг начать нельзя. Только прямые зависимости:
   если 3 зависит от 2, а 2 от 1, у шага 3 пиши только [2].
6. action_type задаётся у каждого шага: «спросить у преподавателя» — people, «написать текст» — study.
7. Не добавляй шаги, которые уже сделаны.
8. note — короткая подсказка к шагу (что взять, на что обратить внимание) или пустая строка.
9. warning — только если задание непонятно без уточнений (нет темы, объёма, неясно, что сдавать): коротко, что уточнить.
   Про нехватку времени не пиши — это посчитают отдельно. Иначе null.
10. task_type и category — для всего задания.

{ACTION_TYPES}

{TASK_TYPES}

{CATEGORIES}

Ответ — только JSON:
{{"task_type": "...", "category": "...", "subtasks": [{{"order": 1, "title": "...", "estimate_min": 60,
"action_type": "study", "depends_on": [], "note": ""}}], "total_estimate_min": 60, "warning": null}}"""


def breakdown_messages(ctx: BreakdownContext) -> list[Message]:
    lines = [f"Задание: {ctx.title}"]
    if ctx.task_type:
        lines.append(f"Тип задания: {ctx.task_type}")
    if ctx.subject:
        lines.append(f"Предмет: {ctx.subject}")
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
    messages = [Message("system", f"{WHO}\n\n{BREAKDOWN_RULES}"), Message("user", "\n".join(lines))]
    if ctx.previous or ctx.comment:
        prev = "\n".join(
            f"{i}. {s.title} — {s.estimate_min} мин" for i, s in enumerate(ctx.previous, 1)
        )
        redo = ["Прошлый вариант разбивки:", prev] if prev else []
        if ctx.comment:
            redo.append(f"Комментарий студентки: «{ctx.comment.strip()}»")
        redo.append("Сделай новую разбивку с учётом комментария.")
        messages.append(Message("user", "\n".join(redo)))
    return messages


# ---------- разбор свободного текста ----------


@dataclass(frozen=True)
class ParseContext:
    text: str
    now: datetime  # настенное время пользователя
    subjects: Sequence[str] = field(default_factory=tuple)


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


def _subjects_line(subjects: Sequence[str]) -> str:
    if not subjects:
        return "Предметов в списке нет — subject всегда пустая строка."
    return (
        "Предметы студентки (subject — одно название из списка, точно как написано, или пустая строка):\n"
        + "\n".join(f"- {s}" for s in subjects)
    )


def parse_messages(ctx: ParseContext) -> list[Message]:
    system = f"""{WHO}

Задача: по сообщению студентки понять, что это, и заполнить карточку.

kind:
- task — учебное или рабочее задание (ДЗ, реферат, доклад, прочитать, подготовиться), обычно со сроком;
- backlog — бытовое или личное дело без жёсткого срока («записаться к стоматологу»);
- event — встреча или мероприятие с точным временем начала.

title — короткое название, до 80 символов, без даты и лишних слов: «Реферат о муссонах»,
а не «надо до пятницы сдать реферат по климатологии про муссоны».
task_type — тип задания; для дел и событий — other.
subject — если в сообщении упомянут предмет из списка (в любом падеже, сокращённо или по теме,
например «по гидрологии» → «Гидрология»), иначе пустая строка.
description — только требования, которые есть в самом сообщении (объём, тема, оформление),
коротко и без даты. Ничего не придумывай и не дописывай от себя. Нет требований — пустая строка.
action_type — когда это уместно делать: people / institutions / study / outside / home / personal.

{DATE_RULES}

{TASK_TYPES}

{ACTION_TYPES}

Ответ — только JSON по схеме."""
    user = "\n".join(
        [
            f"Сегодня: {fmt_date(ctx.now.date())}, сейчас {ctx.now:%H:%M}",
            calendar(ctx.now.date()),
            _subjects_line(ctx.subjects),
            f"Сообщение:\n{_block(ctx.text[:6000])}",
        ]
    )
    return [Message("system", system), Message("user", user)]


# ---------- фото задания ----------


def photo_messages(ctx: ParseContext) -> list[Message]:
    """Фото доски, листка или экрана с заданием. `ctx.text` — подпись к фото (может быть пустой)."""
    system = f"""{WHO}

Задача: на фото — задание (доска, листок, слайд, экран). Перепиши его и заполни карточку.

text — весь текст задания с фото, как написан (формулы — как получится, обычным текстом).
Если текста не видно — пустая строка.
title — короткое название задания, до 80 символов.

{DATE_RULES}

{TASK_TYPES}

Ответ — только JSON по схеме."""
    lines = [
        f"Сегодня: {fmt_date(ctx.now.date())}",
        calendar(ctx.now.date()),
        _subjects_line(ctx.subjects),
    ]
    if ctx.text.strip():
        lines.append(f"Подпись студентки к фото:\n{_block(ctx.text[:2000])}")
    return [Message("system", system), Message("user", "\n".join(lines))]

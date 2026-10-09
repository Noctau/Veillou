"""Быстрый ввод: из строки «реферат климатология до 15 окт» достаёт название, дату,
время, предмет и подсказку, что это (задание / дело в ящик / событие).

Детерминированно и мгновенно, без ИИ и без БД. Время — настенное в TZ `now`.

Что понимает:
- даты: «15 окт», «15 октября 2027», «15.10», «15/10/26», «сегодня», «завтра»,
  «послезавтра», «в пятницу», «к пт», «в следующую среду», «через 3 дня»,
  «через 2 недели», «через две недели», «через месяц», «через 2 часа»,
  «до конца недели / месяца»,
  «на следующей неделе»;
- время: «в 14», «в 14:30», «в 9 утра», «в 7 вечера», «к 18:00», «14:30»,
  «утром / днём / вечером», «с 14 до 16»; длительность «на 2 часа», «на 30 мин»;
- предмет — по названию, короткому имени и синонимам, с учётом падежей
  («по климатологии», «клим»);
- тип задания — по словам «реферат», «доклад», «дз», «лаба», «прочитать»…

Дедлайн (`is_deadline`) — если перед датой стоит «до» / «к» или есть слово
«дедлайн / срок / сдать». Дата без времени как дедлайн — конец дня (23:59).
"""

import datetime as dt
import re
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from dateutil.relativedelta import relativedelta

from app.domain.enums import ActionTypeKey, TaskType


class KindHint(StrEnum):
    task = "task"
    backlog = "backlog"
    event = "event"


@dataclass(frozen=True)
class SubjectRef:
    id: Hashable
    names: tuple[str, ...]  # название, короткое имя, синонимы


@dataclass(frozen=True)
class ParseResult:
    title: str
    date: dt.date | None = None
    time: dt.time | None = None
    end_time: dt.time | None = None
    duration_min: int | None = None
    # date + time (или 23:59) в TZ `now`; только если есть дата
    deadline: datetime | None = None
    is_deadline: bool = False
    subject_id: Hashable | None = None
    task_type: TaskType | None = None
    action_type: ActionTypeKey | None = None
    kind_hint: KindHint = KindHint.backlog


END_OF_DAY = time(23, 59)

# «через две недели»: числа словами (длинные формы раньше коротких — для regex)
NUMBER_WORDS = {
    "одну": 1,
    "один": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
}

MONTHS = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}

WEEKDAYS: list[tuple[int, str]] = [
    (0, r"пн|пон|понедельник[а-я]*"),
    (1, r"вт|вторник[а-я]*"),
    (2, r"ср|сред[аеуы]"),
    (3, r"чт|чет|четверг[а-я]*"),
    (4, r"пт|пятниц[аеуы]"),
    (5, r"сб|суб|суббот[аеуы]"),
    (6, r"вс|воскресень[еяю]"),
]

TASK_TYPES: list[tuple[TaskType, str]] = [
    (TaskType.exam_prep, r"подготов[а-я]*\s+к\s+(?:экзамен|зачет|коллоквиум|контрольн)[а-я]*"),
    (TaskType.exam_prep, r"(?:экзамен|зачет|коллоквиум|контрольн)[а-я]*"),
    (TaskType.essay, r"реферат[а-я]*|эссе"),
    (TaskType.report, r"доклад[а-я]*|презентаци[а-я]*|выступлени[а-я]*"),
    (TaskType.coursework, r"курсов(?:ая|ую|ой)|курсач[а-я]*"),
    (TaskType.lab, r"лаб[а-я]*|практикум[а-я]*"),
    (TaskType.homework, r"дз|домашк[а-я]*|домашн[а-я]*\s+задани[а-я]*|упражнени[а-я]*"),
    (TaskType.reading, r"(?:про|до)?чит[а-я]*|прочест[а-я]*|глав[а-я]*"),
]

# Глаголы учёбы без явного типа: тоже задание
STUDY_VERBS = r"сдать|написать|решить|подготовить|выучить|доделать|оформить|отправить"

# Тип действия по словам (ТЗ §4.8). Порядок важен: первое совпадение побеждает.
ACTION_TYPES: list[tuple[ActionTypeKey, str]] = [
    (
        ActionTypeKey.institutions,
        r"деканат[а-я]*|библиотек[а-я]*|врач[а-я]*|стоматолог[а-я]*|поликлиник[а-я]*|"
        r"больниц[а-я]*|мфц|банк[а-я]*|паспорт[а-я]*|справк[а-я]*|военкомат[а-я]*|"
        r"налогов[а-я]*|нотариус[а-я]*|записаться|запись",
    ),
    (
        ActionTypeKey.people,
        r"научрук[а-я]*|руководител[а-я]*|препод[а-я]*|старост[а-я]*|куратор[а-я]*|"
        r"одногруппник[а-я]*|позвонить|созвониться|спросить|договориться|согласовать",
    ),
    (
        ActionTypeKey.outside,
        r"купить|магазин[а-я]*|аптек[а-я]*|посылк[а-я]*|почт[а-я]*|забрать|отнести|"
        r"химчистк[а-я]*|ремонт[а-я]*",
    ),
    (
        ActionTypeKey.home,
        r"убра[а-я]*|уборк[а-я]*|постира[а-я]*|стирк[а-я]*|приготовить|готовк[а-я]*|"
        r"помыть|пропылесосить|разобрать|погладить|полить|вынести",
    ),
    (
        ActionTypeKey.personal,
        r"спорт[а-я]*|зал|бассейн[а-я]*|йог[а-я]*|пробежк[а-я]*|кино|прогулк[а-я]*|"
        r"погулять|подруг[а-я]*|друз[а-я]*|день\s+рождения",
    ),
]


def guess_action_type(text: str) -> ActionTypeKey | None:
    """Тип действия по словам: «записаться к врачу» → учреждения. Без учёбы."""
    normalized = _normalize(text)
    for key, pattern in ACTION_TYPES:
        if re.search(_b(f"(?:{pattern})"), normalized):
            return key
    return None


WORD = r"[0-9a-zа-я]+"
_word_re = re.compile(WORD)


def _normalize(text: str) -> str:
    # Той же длины, что исходник: позиции совпадений переносятся на оригинал
    text = text.lower().replace("ё", "е")
    # Латинская «c» вместо русской «с» («c 10 до 12») — частая опечатка
    return re.sub(r"(?<![a-z])c(?![a-z])", "с", text)


class _Scanner:
    """Ищет паттерны по нормализованному тексту, помечая занятые участки."""

    def __init__(self, text: str) -> None:
        self.original = text
        self.text = _normalize(text)
        self.taken: list[tuple[int, int]] = []

    def free(self, start: int, end: int) -> bool:
        return all(end <= a or start >= b for a, b in self.taken)

    def find(self, pattern: str) -> re.Match[str] | None:
        for m in re.finditer(pattern, self.text):
            if self.free(m.start(), m.end()):
                return m
        return None

    def take(self, m: re.Match[str], start: int | None = None) -> None:
        self.taken.append((m.start() if start is None else start, m.end()))

    def rest(self) -> str:
        chars = list(self.original)
        for a, b in self.taken:
            for i in range(a, b):
                chars[i] = " "
        return "".join(chars)


def _b(pattern: str) -> str:
    """Граница слова для кириллицы (\\b в re работает и для неё, но явно надёжнее)."""
    return rf"(?<![0-9a-zа-я]){pattern}(?![0-9a-zа-я])"


PREP = r"(?:(?P<prep>до|к|ко|в|во|на|с|по|не\s+позже)\s+)?"


def _next_weekday(today: date, weekday: int, *, next_week: bool, this_week: bool) -> date:
    monday = today - timedelta(days=today.weekday())
    if next_week:
        return monday + timedelta(days=7 + weekday)
    candidate = monday + timedelta(days=weekday)
    if this_week and candidate >= today:
        return candidate
    days = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


def _hour(h: int, m: int, suffix: str | None) -> time | None:
    if suffix:
        if suffix.startswith(("веч", "дня")) and h < 12:
            h += 12
        elif suffix.startswith("ноч") and h == 12:
            h = 0
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return time(h, m)


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _future(d: date, today: date, explicit_year: bool) -> date:
    """«15 окт», сказанное 20 октября, — это следующий год."""
    if explicit_year or d >= today:
        return d
    return d.replace(year=d.year + 1) if _safe_date(d.year + 1, d.month, d.day) else d


def _word_match(name: str, token: str) -> bool:
    if token == name:
        return True
    # Короткое имя — начало слова: «клим» → «климатологии»
    if len(name) >= 4 and token.startswith(name):
        return True
    # Падежи: «климатология» ~ «климатологии»
    stem = name[:-2] if len(name) >= 6 else name[:-1] if len(name) >= 5 else None
    return stem is not None and token.startswith(stem) and len(token) - len(stem) <= 4


def _match_subject(
    sc: _Scanner, subjects: Sequence[SubjectRef]
) -> tuple[Hashable, int, int] | None:
    tokens = [m for m in _word_re.finditer(sc.text) if sc.free(m.start(), m.end())]
    best: dict[Hashable, tuple[int, int, int]] = {}  # id -> (score, start, end)
    for subject in subjects:
        for raw in subject.names:
            words = _word_re.findall(_normalize(raw))
            if not words:
                continue
            for i in range(len(tokens) - len(words) + 1):
                window = tokens[i : i + len(words)]
                if all(_word_match(w, t.group()) for w, t in zip(words, window, strict=True)):
                    score = sum(len(w) for w in words)
                    if score > best.get(subject.id, (0, 0, 0))[0]:
                        best[subject.id] = (score, window[0].start(), window[-1].end())
    if not best:
        return None
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
    if len(ranked) > 1 and ranked[0][1][0] == ranked[1][1][0]:
        return None  # неоднозначно
    subject_id, (_, start, end) = ranked[0]
    return subject_id, start, end


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    dangling = r"(?:до|к|ко|в|во|на|с|по|не позже|срок|дедлайн)"
    for _ in range(3):
        text = re.sub(rf"(?i)(?:^|\s){dangling}$", "", text).strip(" ,.;:—–-")
        text = re.sub(r"(?i)^(?:до|к|ко|срок|дедлайн)\s", "", text).strip(" ,.;:—–-")
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text[:1].upper() + text[1:]


def parse(text: str, now: datetime, subjects: Sequence[SubjectRef] = ()) -> ParseResult:
    """Разбирает строку быстрого ввода. `now` — aware, в TZ пользователя."""
    if now.tzinfo is None:
        raise ValueError("now должен быть с часовым поясом")
    today = now.date()
    sc = _Scanner(text)
    day: date | None = None
    at: time | None = None
    end_at: time | None = None
    duration: int | None = None
    is_deadline = False

    def mark_deadline(prep: str | None) -> None:
        nonlocal is_deadline
        if prep and (prep in ("до", "к", "ко") or prep.startswith("не")):
            is_deadline = True

    # «с 14 до 16», «с 9:30 до 11»
    if m := sc.find(_b(r"с\s+(\d{1,2})(?:[:.](\d{2}))?\s+до\s+(\d{1,2})(?:[:.](\d{2}))?")):
        t1 = _hour(int(m[1]), int(m[2] or 0), None)
        t2 = _hour(int(m[3]), int(m[4] or 0), None)
        if t1 and t2:
            at, end_at = t1, t2
            sc.take(m)

    # «через 2 недели», «через две недели», «через час», «через пару дней»
    words = "|".join(NUMBER_WORDS)
    rel = (
        rf"через\s+(?P<n>\d+|пару|полчаса|{words})?\s*"
        r"(?P<unit>мин[а-я]*|час[а-я]*|ч|дн[а-я]*|день|недел[а-я]*|нед|мес[а-я]*)?"
    )
    if (m := sc.find(_b(rel))) and (m["unit"] or m["n"] == "полчаса"):
        n_raw = m["n"]
        if n_raw in NUMBER_WORDS:
            n = NUMBER_WORDS[n_raw]
        else:
            n = 2 if n_raw == "пару" else 1 if n_raw in (None, "полчаса") else int(n_raw)
        unit = m["unit"] or "мин"
        if n_raw == "полчаса":
            n, unit = 30, "мин"
        if unit.startswith(("мин", "час", "ч")):
            minutes = n if unit.startswith("мин") else n * 60
            moment = now + timedelta(minutes=minutes)
            # Округляем вверх до 5 минут
            moment += timedelta(minutes=-moment.minute % 5, seconds=-moment.second)
            day, at = moment.date(), moment.time().replace(second=0, microsecond=0)
        elif unit.startswith(("дн", "день")):
            day = today + timedelta(days=n)
        elif unit.startswith("нед"):
            day = today + timedelta(weeks=n)
        else:
            day = today + relativedelta(months=n)
        sc.take(m)

    # «до 15 окт», «15 октября 2027»
    if day is None:
        months = "|".join(MONTHS)
        pattern = PREP + rf"(\d{{1,2}})\s+({months})[а-я]*\.?(?:\s+(\d{{4}}))?(?:\s*г\.?)?"
        if m := sc.find(_b(pattern)):
            year = int(m[4]) if m[4] else today.year
            parsed = _safe_date(year, MONTHS[m[3]], int(m[2]))
            if parsed:
                day = _future(parsed, today, bool(m[4]))
                mark_deadline(m["prep"])
                sc.take(m)

    # «15.10», «15/10/26» (но не «в 14.30» — это время)
    if day is None:
        pattern = r"(?P<prep>до|к|ко|на|по)?\s*(?<!в )(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?"
        if m := sc.find(_b(pattern)):
            year = int(m[4]) if m[4] else today.year
            if year < 100:
                year += 2000
            parsed = _safe_date(year, int(m[3]), int(m[2]))
            if parsed:
                day = _future(parsed, today, bool(m[4]))
                mark_deadline(m["prep"])
                sc.take(m)

    # «до конца недели», «на следующей неделе», «до конца месяца»
    if day is None:
        if m := sc.find(_b(r"(?P<prep>до|к)?\s*конц[а-я]*\s+(недел[а-я]*|месяц[а-я]*)")):
            if m[2].startswith("нед"):
                day = today + timedelta(days=6 - today.weekday())
            else:
                day = today + relativedelta(day=31)
            is_deadline = True
            sc.take(m)
        elif m := sc.find(_b(r"на\s+(следующ[а-я]*|след\.?|этой)\s+неделе")):
            sunday = today + timedelta(days=6 - today.weekday())
            day = sunday if m[1] == "этой" else sunday + timedelta(days=7)
            sc.take(m)

    # «сегодня», «завтра», «послезавтра»
    if day is None:
        offsets = {"сегодня": 0, "завтра": 1, "послезавтра": 2}
        if m := sc.find(_b(PREP + r"(сегодня|послезавтра|завтра)")):
            day = today + timedelta(days=offsets[m[2]])
            mark_deadline(m["prep"])
            sc.take(m)

    # «к пятнице», «в следующую среду», «в пт»
    if day is None:
        for weekday, forms in WEEKDAYS:
            which_re = r"(?:(?P<which>следующ[а-я]*|след\.?|эт[аоиуы][а-я]*)\s+)?"
            pattern = PREP + which_re + f"(?:{forms})"
            if m := sc.find(_b(pattern)):
                which = m["which"] or ""
                day = _next_weekday(
                    today,
                    weekday,
                    next_week=which.startswith("след"),
                    this_week=which.startswith("эт"),
                )
                mark_deadline(m["prep"])
                sc.take(m)
                break

    # Длительность: «на 2 часа», «на 30 мин», «на час», «на полчаса»
    pattern = r"на\s+(?:(\d+(?:[.,]5)?)\s*)?(час[а-я]*|ч|мин[а-я]*|полчаса|пол\s+часа)"
    if m := sc.find(_b(pattern)):
        amount = float(m[1].replace(",", ".")) if m[1] else 1.0
        unit = m[2]
        if "пол" in unit:
            duration = 30
        elif unit.startswith("мин"):
            duration = int(amount)
        else:
            duration = int(amount * 60)
        sc.take(m)

    # Время: «в 14», «в 14:30», «к 18:00», «в 9 утра», «в 2 часа ночи», «14:30»
    if at is None:
        pattern = (
            r"(?P<prep>в|во|к|до|на)\s+(\d{1,2})(?:[:.](\d{2}))?"
            r"(?P<hours>\s*(?:ч\.?|час[а-я]*))?(?:\s*(?P<part>утра|дня|вечера|ночи))?"
            r"(?:\s+(?P<next>[а-я]+))?"
        )
        for m in re.finditer(_b(pattern), sc.text):
            if not sc.free(m.start(), m.end()):
                continue
            mins, part, next_word = m[3], m["part"], m["next"] or ""
            # Голое «в 5» — время, только если это не счёт («в 5 магазинов», «на 2 человека»)
            bare = not (mins or part or m["hours"])
            if bare and (m["prep"] == "на" or re.search(r"(ов|ев|ей|ам|ям|ах|ях|ми)$", next_word)):
                continue
            parsed_time = _hour(int(m[2]), int(mins or 0), part)
            if parsed_time:
                at = parsed_time
                mark_deadline(m["prep"])
                # Следующее слово — не часть времени, его оставляем в названии
                sc.taken.append((m.start(), m.start("next") if m["next"] else m.end()))
                break
    # «14:30», «семинар 14.30» (дата вида 14.10 уже разобрана выше)
    if (
        at is None
        and (m := sc.find(_b(r"(\d{1,2})[:.](\d{2})")))
        and (parsed_time := _hour(int(m[1]), int(m[2]), None))
    ):
        at = parsed_time
        sc.take(m)

    if at is None:
        parts = {"утром": time(9, 0), "днем": time(13, 0), "вечером": time(19, 0)}
        if m := sc.find(_b(r"(утром|днем|вечером)")):
            at = parts[m[1]]
            sc.take(m)

    if m := sc.find(_b(r"(дедлайн|срок)[а-я]*")):
        is_deadline = True
        sc.take(m)

    # Время без даты: сегодня, если ещё впереди, иначе завтра
    if at is not None and day is None:
        day = today if at > now.time() else today + timedelta(days=1)

    # Тип задания и предмет — по тексту без дат (в названии остаются)
    task_type: TaskType | None = None
    for candidate, pattern in TASK_TYPES:
        if sc.find(_b(f"(?:{pattern})")):
            task_type = candidate
            break
    has_study_verb = sc.find(_b(f"(?:{STUDY_VERBS})")) is not None

    subject_id: Hashable | None = None
    if found := _match_subject(sc, subjects):
        subject_id, start, end = found
        before = sc.text[:start].rstrip()
        cut_from = start
        if before.endswith(" по") or before == "по":
            cut_from = before.rfind("по")
        title_without = _clean_title(sc.rest()[:cut_from] + sc.rest()[end:])
        # Если от названия ничего не остаётся — предмет в нём оставляем
        if title_without:
            sc.taken.append((cut_from, end))

    title = _clean_title(sc.rest()) or _clean_title(text)

    deadline = None
    if day is not None:
        deadline = datetime.combine(day, at or END_OF_DAY, tzinfo=now.tzinfo)

    if has_study_verb and day is not None and at is None:
        is_deadline = True

    action_type = guess_action_type(title)
    if action_type is None and (task_type or subject_id is not None or has_study_verb):
        action_type = ActionTypeKey.study

    kind: KindHint
    if at is not None and not is_deadline and task_type is None:
        kind = KindHint.event
    elif task_type or subject_id is not None or is_deadline:
        kind = KindHint.task
    else:
        kind = KindHint.backlog

    return ParseResult(
        title=title,
        date=day,
        time=at,
        end_time=end_at,
        duration_min=duration,
        deadline=deadline,
        is_deadline=is_deadline,
        subject_id=subject_id,
        task_type=task_type,
        action_type=action_type,
        kind_hint=kind,
    )


# ---------- когда звать ИИ (M10.5) ----------

# Длиннее — скорее всего пересланный текст задания, а не строка быстрого ввода
AI_TEXT_LEN = 80


def needs_ai(text: str, p: ParseResult) -> bool:
    """Разбор неуверенный — стоит спросить ИИ.

    Длинный или многострочный текст (пересланное задание) или задание без
    срока либо без предмета. Короткие дела и события с временем ИИ не нужны.
    """
    text = text.strip()
    if "\n" in text or len(text) > AI_TEXT_LEN:
        return True
    return p.kind_hint == KindHint.task and (p.date is None or p.subject_id is None)


_DATE_CUE = re.compile(
    r"\d|янв|фев|мар|апр|ма[йя]|июн|июл|авг|сен|окт|ноя|дек|понедельн|вторник|сред[уаы]|"
    r"четверг|пятниц|суббот|воскресен|\bпн\b|\bвт\b|\bср\b|\bчт\b|\bпт\b|\bсб\b|\bвс\b|"
    r"сегодня|завтра|послезавтра|через|недел|месяц|выходн|дедлайн|срок",
    re.IGNORECASE,
)


def has_date_cue(text: str) -> bool:
    """Есть ли в тексте хоть какой-то намёк на дату. Нет — срок от ИИ выдуман."""
    return bool(_DATE_CUE.search(text))

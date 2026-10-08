"""Проекты v2 (M13): недельная норма и отставание по этапам. Чистые функции."""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

# Резерв нормы — блоками примерно по полтора часа, кратно 15 минутам
RESERVE_CHUNK_MIN = 90
# Меньше получаса резерв не ставим (и недобор такого размера — не угроза)
MIN_RESERVE_MIN = 30
GRID_MIN = 15
# Сколько недель вперёд резервируется норма: текущая и следующая
QUOTA_WEEKS = 2


def reserve_chunks(minutes: int) -> list[int]:
    """Недостающие минуты нормы → длительности резервных блоков.

    Блоков столько, чтобы каждый был не длиннее ~90 минут; длины равные,
    округлены вверх до 15 минут (норма лучше с запасом, чем с недобором).
    """
    if minutes < MIN_RESERVE_MIN:
        return []
    count = math.ceil(minutes / RESERVE_CHUNK_MIN)
    size = math.ceil(minutes / count / GRID_MIN) * GRID_MIN
    return [max(size, MIN_RESERVE_MIN)] * count


def reserve_title(project_title: str) -> str:
    return f"{project_title} — работа над проектом"[:300]


def week_target(norm_min: int, done_before_today: int, days_left: int) -> int:
    """Сколько минут нормы ставить на остаток текущей недели.

    Не больше, чем осталось до нормы, и не больше доли недели, которая
    осталась (пропущенное в начале недели не набиваем в последние дни).
    `days_left` — включая сегодня (понедельник — 7, воскресенье — 1).
    """
    remaining = norm_min - done_before_today
    share = math.ceil(norm_min * max(0, min(days_left, 7)) / 7)
    return max(0, min(remaining, share))


@dataclass(frozen=True)
class MilestoneDates:
    date: date | None
    done: bool


def behind_days(milestones: Iterable[MilestoneDates], today: date) -> int:
    """Отставание проекта: на сколько дней просрочен самый старый невыполненный этап."""
    overdue = [m.date for m in milestones if not m.done and m.date is not None and m.date < today]
    return (today - min(overdue)).days if overdue else 0


# ---------- этапы от ИИ (M13.2) ----------

MAX_SUGGESTED = 12


@dataclass(frozen=True)
class RawMilestone:
    title: str
    date: date | None
    note: str = ""


def _key(title: str) -> str:
    return " ".join(title.casefold().replace("ё", "е").split()).strip(" .")


def normalize_milestones(
    raw: Iterable[RawMilestone],
    *,
    today: date,
    deadline: date | None,
    existing: Iterable[str] = (),
) -> list[RawMilestone]:
    """Чистит этапы от ИИ: без пустых и повторов (в т. ч. уже существующих),
    даты — от сегодня до итогового срока (прошедшая дата убирается, поздняя —
    прижимается к сроку), по порядку дат, этапы без даты — в конце."""
    seen = {_key(t) for t in existing}
    limit = deadline if deadline is not None and deadline >= today else None
    result: list[RawMilestone] = []
    for m in raw:
        title = " ".join(m.title.split())[:300]
        key = _key(title)
        if not key or key in seen:
            continue
        seen.add(key)
        day = m.date
        if day is not None and day < today:
            day = None
        if day is not None and limit is not None and day > limit:
            day = limit
        result.append(RawMilestone(title, day, " ".join(m.note.split())))
    result.sort(key=lambda m: (m.date is None, m.date or date.max))
    return result[:MAX_SUGGESTED]

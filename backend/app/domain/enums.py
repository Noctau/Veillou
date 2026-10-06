"""Перечисления предметной области. Общие для domain, моделей и API-схем."""

from enum import StrEnum


class Parity(StrEnum):
    """Чётность недели: числитель = odd, знаменатель = even."""

    odd = "odd"
    even = "even"


class RuleParity(StrEnum):
    """Когда идёт пара: каждую неделю, по числителям или по знаменателям."""

    all = "all"
    odd = "odd"
    even = "even"


class ClassType(StrEnum):
    lecture = "lecture"
    seminar = "seminar"
    lab = "lab"
    other = "other"


class ControlForm(StrEnum):
    """Форма контроля по предмету."""

    exam = "exam"
    credit = "credit"  # зачёт
    graded_credit = "graded_credit"  # дифзачёт
    coursework = "coursework"
    none = "none"


class EventKind(StrEnum):
    class_ = "class"  # пара (из ClassRule)
    personal = "personal"  # личное (жёсткое)
    rest = "rest"  # отдых (жёсткое)
    subtask = "subtask"  # подзадача (гибкое, M4+)
    backlog = "backlog"  # дело из ящика (гибкое, M11)
    exam_prep = "exam_prep"  # подготовка к экзамену (гибкое, M12)


FIXED_KINDS = frozenset({EventKind.class_, EventKind.personal, EventKind.rest})


class EventStatus(StrEnum):
    planned = "planned"
    done = "done"
    cancelled = "cancelled"
    missed = "missed"


class TemplateType(StrEnum):
    """Откуда материализовано вхождение."""

    class_rule = "class_rule"
    recurring = "recurring"  # RecurringEvent (личные блоки и отдых с повтором)


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

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


# ---------- задания (M4.2) ----------


class TaskType(StrEnum):
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
    backlog_item = "backlog_item"


# ---------- долгий ящик (M4.6) ----------


class BacklogStatus(StrEnum):
    active = "active"
    done = "done"
    archived = "archived"  # «неактуально»


class BacklogCondition(StrEnum):
    """Условия дела — фиксированный набор чипов, без свободного текста."""

    weekday_daytime = "weekday_daytime"  # только в будни днём
    on_class_days = "on_class_days"  # в дни пар (в городе)
    needs_laptop = "needs_laptop"  # нужен ноутбук
    institution_hours = "institution_hours"  # в часы работы учреждений


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

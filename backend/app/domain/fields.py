"""Пользовательские поля (Part 2, M16.1): описания полей и их значения.

Поле описывает тип сферы (позже — тип занятости и правило расписания). Значения
хранятся в JSONB как `{field_id: value}`. Поля на план не влияют никогда.

- Неизвестные ключи при сохранении отбрасываются.
- Переименование меняет только `label`: `id` стабилен, значения на месте.
- Удалённое поле остаётся в описаниях с `deleted=True`: значения в JSONB не теряются,
  но не показываются и не правятся. Вернуть поле — снять флаг.

Форматы значений:
- text — строка; number — int | float; bool — true/false;
- select — строка из `options`; multiselect — список строк из `options`;
- date — "YYYY-MM-DD";
- contact — `{name, role, phone, email, link, note}` (все необязательны, хоть одно есть);
- link — `{title, url}` (http/https);
- area_ref — id сферы строкой (существование проверяет сервис).

У text, contact, link и area_ref может быть `multiple`: значение — список.
"""

import math
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from app.domain.enums import FieldType

TEXT_MAX = 2000
LABEL_MAX = 60
OPTIONS_MAX = 50
OPTION_MAX = 100
ITEMS_MAX = 50
FIELDS_MAX = 30

# Типы, у которых бывает «много значений»
MULTIPLE_TYPES = frozenset({FieldType.text, FieldType.contact, FieldType.link, FieldType.area_ref})
CHOICE_TYPES = frozenset({FieldType.select, FieldType.multiselect})
CONTACT_KEYS = ("name", "role", "phone", "email", "link", "note")

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_PHONE_RE = re.compile(r"^\+?[\d\s()\-.]{5,}$")


class FieldError(ValueError):
    """Описания полей или значения не прошли проверку. Текст — для пользователя."""


@dataclass(frozen=True)
class FieldDef:
    id: str
    label: str
    type: FieldType
    options: tuple[str, ...] = ()
    multiple: bool = False
    show_in_reminder: bool = False
    required: bool = False
    deleted: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type.value,
            "options": list(self.options),
            "multiple": self.multiple,
            "show_in_reminder": self.show_in_reminder,
            "required": self.required,
            "deleted": self.deleted,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "FieldDef":
        return cls(
            id=str(raw["id"]),
            label=str(raw.get("label", "")),
            type=FieldType(raw["type"]),
            options=tuple(raw.get("options") or ()),
            multiple=bool(raw.get("multiple", False)),
            show_in_reminder=bool(raw.get("show_in_reminder", False)),
            required=bool(raw.get("required", False)),
            deleted=bool(raw.get("deleted", False)),
        )


def parse_defs(raw: Sequence[Mapping[str, Any]] | None) -> list[FieldDef]:
    return [FieldDef.from_json(r) for r in raw or ()]


def dump_defs(defs: Sequence[FieldDef]) -> list[dict[str, Any]]:
    return [d.to_json() for d in defs]


def active(defs: Sequence[FieldDef]) -> list[FieldDef]:
    return [d for d in defs if not d.deleted]


# ---------- описания ----------


def _check_def(d: FieldDef) -> list[str]:
    problems = []
    name = d.label or d.id
    if not d.label.strip():
        problems.append("у поля нет названия")
    elif len(d.label) > LABEL_MAX:
        problems.append(f"«{name}»: название длиннее {LABEL_MAX} символов")
    if d.type in CHOICE_TYPES:
        if not d.options:
            problems.append(f"«{name}»: нет вариантов выбора")
        if len(d.options) > OPTIONS_MAX:
            problems.append(f"«{name}»: вариантов больше {OPTIONS_MAX}")
        if len({o.casefold() for o in d.options}) != len(d.options):
            problems.append(f"«{name}»: варианты повторяются")
        if any(not o.strip() or len(o) > OPTION_MAX for o in d.options):
            problems.append(f"«{name}»: пустой или слишком длинный вариант")
    elif d.options:
        problems.append(f"«{name}»: варианты бывают только у выбора из списка")
    if d.multiple and d.type not in MULTIPLE_TYPES:
        problems.append(f"«{name}»: несколько значений у этого типа не бывает")
    return problems


def _new_id(taken: set[str]) -> str:
    n = 1
    while f"f{n}" in taken:
        n += 1
    return f"f{n}"


def merge_defs(
    old: Sequence[FieldDef], new: Sequence[FieldDef], *, keep_ids: bool = False
) -> list[FieldDef]:
    """Новый список полей поверх старого — без потери данных.

    - Поле с id из старого списка — то же поле: можно переименовать, поменять
      варианты и флаги, но не тип (значения другого типа станут мусором).
    - Поле с пустым или незнакомым id — новое: id выдаётся `f1`, `f2`, … (не занятые
      ни живыми, ни удалёнными полями). С `keep_ids` (импорт сборки) незнакомый
      допустимый id остаётся — на него ссылаются значения из той же сборки.
    - Старое поле, которого нет в новом списке, остаётся с `deleted=True` в конце.

    Порядок живых полей — как в `new`. Ошибки — `FieldError` со всеми проблемами.
    """
    old_by_id = {d.id: d for d in old}
    taken = set(old_by_id)
    problems: list[str] = []
    result: list[FieldDef] = []
    seen: set[str] = set()
    for d in new:
        d = replace(
            d,
            label=d.label.strip(),
            options=tuple(o.strip() for o in d.options),
            deleted=False,
        )
        prev = old_by_id.get(d.id)
        if prev is not None and d.id not in seen:
            if prev.type != d.type:
                problems.append(f"«{d.label}»: тип поля не меняется — создайте новое поле")
        elif keep_ids and prev is None and d.id not in taken and _ID_RE.match(d.id):
            taken.add(d.id)
        else:
            d = replace(d, id=_new_id(taken))
            taken.add(d.id)
        seen.add(d.id)
        problems += _check_def(d)
        result.append(d)
    labels = [d.label.casefold() for d in result]
    if len(set(labels)) != len(labels):
        problems.append("названия полей повторяются")
    if len(result) > FIELDS_MAX:
        problems.append(f"полей больше {FIELDS_MAX}")
    if problems:
        raise FieldError("; ".join(dict.fromkeys(problems)))
    result += [replace(d, deleted=True) for d in old if d.id not in seen]
    return result


def validate_defs(defs: Sequence[FieldDef]) -> None:
    """Проверка готового списка (сид, миграция, импорт сборки)."""
    problems = [p for d in defs for p in _check_def(d)]
    ids = [d.id for d in defs]
    if len(set(ids)) != len(ids):
        problems.append("id полей повторяются")
    problems += [f"id «{i}»: латиница, цифры и _" for i in ids if not _ID_RE.match(i)]
    labels = [d.label.casefold() for d in active(defs)]
    if len(set(labels)) != len(labels):
        problems.append("названия полей повторяются")
    if problems:
        raise FieldError("; ".join(problems))


# ---------- значения ----------


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        raise FieldError("ожидается текст")
    text = value.strip()
    if len(text) > TEXT_MAX:
        raise FieldError(f"текст длиннее {TEXT_MAX} символов")
    return text or None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        raise FieldError("ожидается число")
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return None
        try:
            value = float(value)
        except ValueError:
            raise FieldError("ожидается число") from None
    if not isinstance(value, int | float) or not math.isfinite(value):
        raise FieldError("ожидается число")
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        return int(value)
    return value


def _bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise FieldError("ожидается да или нет")
    return value


def _choice(value: Any, options: tuple[str, ...]) -> str | None:
    text = _text(value)
    if text is None:
        return None
    for option in options:
        if option.casefold() == text.casefold():
            return option
    raise FieldError(f"«{text}» нет среди вариантов")


def _date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise FieldError("ожидается дата")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        raise FieldError("ожидается дата ГГГГ-ММ-ДД") from None


def _url(value: Any) -> str:
    text = _text(value)
    if text is None:
        raise FieldError("нет адреса ссылки")
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise FieldError(f"«{text}» — не ссылка http(s)")
    return text


def _link(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        value = {"url": value}
    if not isinstance(value, Mapping):
        raise FieldError("ожидается ссылка")
    if _is_empty(value.get("url")):
        if _is_empty(value.get("title")):
            return None
        raise FieldError("нет адреса ссылки")
    title = value.get("title") or ""
    return {"title": _text(title) or "", "url": _url(value["url"])}


def _contact(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        value = {"name": value}
    if not isinstance(value, Mapping):
        raise FieldError("ожидается контакт")
    cleaned = {}
    for key in CONTACT_KEYS:
        raw = value.get(key)
        if _is_empty(raw):
            continue
        text = _text(raw)
        if text:
            cleaned[key] = text
    if "email" in cleaned and "@" not in cleaned["email"]:
        raise FieldError(f"«{cleaned['email']}» — не email")
    if "link" in cleaned:
        cleaned["link"] = _url(cleaned["link"])
    return cleaned or None


def _area_ref(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise FieldError("ожидается сфера") from None


def _one(d: FieldDef, value: Any) -> Any:
    if _is_empty(value):
        return None
    match d.type:
        case FieldType.text:
            return _text(value)
        case FieldType.number:
            return _number(value)
        case FieldType.bool:
            return _bool(value)
        case FieldType.select:
            return _choice(value, d.options)
        case FieldType.multiselect:
            items = value if isinstance(value, list) else [value]
            chosen = {_choice(v, d.options) for v in items}
            # Порядок — как в вариантах
            return [o for o in d.options if o in chosen] or None
        case FieldType.date:
            return _date(value)
        case FieldType.contact:
            return _contact(value)
        case FieldType.link:
            return _link(value)
        case FieldType.area_ref:
            return _area_ref(value)


def clean_value(d: FieldDef, value: Any) -> Any:
    """Значение одного поля в формате хранения; None — пусто."""
    if not d.multiple:
        if isinstance(value, list) and d.type is not FieldType.multiselect:
            raise FieldError("ожидается одно значение")
        return _one(d, value)
    items = value if isinstance(value, list) else [value]
    if len(items) > ITEMS_MAX:
        raise FieldError(f"значений больше {ITEMS_MAX}")
    cleaned = [c for c in (_one(d, v) for v in items) if c is not None]
    if d.type is FieldType.area_ref:
        cleaned = list(dict.fromkeys(cleaned))
    return cleaned or None


def validate_values(
    defs: Sequence[FieldDef],
    values: Mapping[str, Any] | None,
    *,
    stored: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Очищенные значения для записи в JSONB.

    - ключи не из `defs` отбрасываются; пустые значения не хранятся;
    - значения удалённых полей берутся из `stored` (что было в БД) — их не правят;
    - обязательное живое поле без значения — ошибка.

    Ошибки — `FieldError` со всеми проблемами сразу.
    """
    values = values or {}
    stored = stored or {}
    cleaned: dict[str, Any] = {}
    problems: list[str] = []
    for d in defs:
        if d.deleted:
            if not _is_empty(stored.get(d.id)):
                cleaned[d.id] = stored[d.id]
            continue
        try:
            value = clean_value(d, values.get(d.id))
        except FieldError as exc:
            problems.append(f"«{d.label}»: {exc}")
            continue
        if value is None:
            if d.required:
                problems.append(f"«{d.label}»: обязательное поле")
            continue
        cleaned[d.id] = value
    if problems:
        raise FieldError("; ".join(problems))
    return cleaned


def area_refs(defs: Sequence[FieldDef], values: Mapping[str, Any]) -> set[str]:
    """Id сфер из полей area_ref — сервис проверяет, что они свои и живые."""
    refs: set[str] = set()
    for d in active(defs):
        if d.type is FieldType.area_ref and d.id in values:
            value = values[d.id]
            refs.update(value if isinstance(value, list) else [value])
    return refs


# ---------- показ ----------


def _format_number(value: Any) -> str:
    return str(value).replace(".", ",")


def _format_date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def _format_contact(value: Any) -> str:
    if not isinstance(value, Mapping):
        return str(value)
    head = value.get("name") or ""
    if value.get("role"):
        head = f"{head} ({value['role']})" if head else str(value["role"])
    rest = [str(value[k]) for k in ("phone", "email", "link", "note") if value.get(k)]
    return " · ".join(p for p in (head, *rest) if p)


def _format_link(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("title") or value.get("url") or "")
    return str(value)


def _format_one(d: FieldDef, value: Any, area_names: Mapping[str, str]) -> str:
    match d.type:
        case FieldType.number:
            return _format_number(value)
        case FieldType.bool:
            return "да" if value else "нет"
        case FieldType.multiselect:
            return ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        case FieldType.date:
            return _format_date(value)
        case FieldType.contact:
            return _format_contact(value)
        case FieldType.link:
            return _format_link(value)
        case FieldType.area_ref:
            return area_names.get(str(value), "")
        case _:
            return str(value)


def render_values(
    defs: Sequence[FieldDef],
    values: Mapping[str, Any] | None,
    *,
    only_reminder: bool = False,
    area_names: Mapping[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Подписи и тексты живых полей со значением — в порядке полей.

    Не падает на «старых» значениях (вариант убрали из списка — значение показывается
    как есть). `area_names` — названия сфер для area_ref; неизвестные пропускаются.
    """
    values = values or {}
    names = area_names or {}
    result = []
    for d in active(defs):
        if only_reminder and not d.show_in_reminder:
            continue
        value = values.get(d.id)
        if _is_empty(value):
            continue
        items = value if d.multiple and isinstance(value, list) else [value]
        sep = "; " if d.type is FieldType.contact else ", "
        text = sep.join(t for t in (_format_one(d, v, names) for v in items) if t)
        if text:
            result.append((d.label, text))
    return result


def render_split(
    defs: Sequence[FieldDef],
    values: Mapping[str, Any] | None,
    *,
    only_reminder: bool = False,
    area_names: Mapping[str, str] | None = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Как `render_values`, но значения выбора (select, multiselect) — отдельно и без
    подписи: в строке события они читаются сами по себе («лекция»), остальное —
    кортежами «подпись, текст» в порядке полей."""
    inline: list[str] = []
    rest: list[tuple[str, str]] = []
    for d in active(defs):
        for label, text in render_values(
            [d], values, only_reminder=only_reminder, area_names=area_names
        ):
            if d.type in CHOICE_TYPES:
                inline.append(text)
            else:
                rest.append((label, text))
    return inline, rest

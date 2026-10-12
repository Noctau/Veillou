"""Сборки конфигурации (M21.3): ссылки, сравнение, порядок импорта. Чистые функции
над JSON-словарями сборки (`schemas/bundle.ConfigBundle.model_dump(mode="json")`).

Кирпич узнаётся не по `ref` (у каждой сборки свои), а по **естественному ключу**:
название (с учётом родителя — сфера ищется в своём типе и периоде) или, у безымянных
правил, всё содержимое. Ссылки в ключе и содержимом заменены ключами целей, так что
две сборки сравниваются независимо от их `ref`.
"""

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

# Разделы в порядке импорта: цель ссылки всегда раньше ссылающегося
SECTIONS: tuple[str, ...] = (
    "categories",
    "action_types",
    "task_types",
    "area_types",
    "periods",
    "days_off",
    "slot_grids",
    "areas",
    "event_types",
    "budgets",
    "day_profiles",
    "day_profile_rules",
    "schedule_rules",
    "event_rules",
)

# Поле-ссылка → раздел цели. Список — несколько ссылок
REFS: dict[str, dict[str, str]] = {
    "action_types": {"category": "categories"},
    "task_types": {"action_type": "action_types", "category": "categories"},
    "days_off": {"period": "periods"},
    "slot_grids": {"period": "periods"},
    "areas": {"area_type": "area_types", "period": "periods"},
    "event_types": {"default_area_type": "area_types"},
    "budgets": {"action_types": "action_types", "event_types": "event_types"},
    "day_profile_rules": {"profile": "day_profiles", "event_type": "event_types"},
    "schedule_rules": {
        "event_type": "event_types",
        "area": "areas",
        "period": "periods",
        "slot_grid": "slot_grids",
    },
    "event_rules": {
        "event_type": "event_types",
        "schedule_rule": "schedule_rules",
        "action_type": "action_types",
        "task_type": "task_types",
    },
}
SETTINGS_REFS = {"default_action_type": "action_types"}

# Поля естественного ключа; None — ключ = всё содержимое (правила без названия)
NATURAL: dict[str, tuple[str, ...] | None] = {
    "categories": ("name",),
    "action_types": ("name",),
    "task_types": ("name",),
    "area_types": ("name",),
    "periods": ("name",),
    "days_off": ("period", "date_from", "date_to"),
    "slot_grids": ("period", "name"),
    "areas": ("area_type", "period", "name"),
    "event_types": ("name",),
    "budgets": ("name",),
    "day_profiles": ("name",),
    "day_profile_rules": None,
    "schedule_rules": None,
    "event_rules": None,
}

# Разделы, где порядок задаёт пользователь (позиция в интерфейсе)
ORDERED = frozenset(
    {
        "categories",
        "action_types",
        "task_types",
        "area_types",
        "event_types",
        "budgets",
        "day_profiles",
        "day_profile_rules",
        "event_rules",
    }
)

Bundle = Mapping[str, Any]
Status = Literal["added", "changed", "skipped"]


class BundleError(ValueError):
    """Сборка битая: неизвестные или повторяющиеся ссылки."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _items(bundle: Bundle, section: str) -> list[dict[str, Any]]:
    return list(bundle.get(section) or [])


def _targets(section: str, item: Mapping[str, Any]) -> Iterable[tuple[str, str, str]]:
    """(поле, раздел цели, ref) всех ссылок кирпича."""
    for name, target in REFS.get(section, {}).items():
        value = item.get(name)
        for ref in value if isinstance(value, list) else [value]:
            if ref is not None:
                yield name, target, ref


def check_refs(bundle: Bundle) -> None:
    """`BundleError`, если `ref` повторяются в разделе или ссылки ведут в никуда."""
    problems: list[str] = []
    known: dict[str, set[str]] = {}
    for section in SECTIONS:
        refs = [item["ref"] for item in _items(bundle, section)]
        if dups := sorted({r for r in refs if refs.count(r) > 1}):
            problems.append(f"{section}: повторяются ref {', '.join(dups)}")
        known[section] = set(refs)
    for section in SECTIONS:
        for item in _items(bundle, section):
            for name, target, ref in _targets(section, item):
                if ref not in known[target]:
                    problems.append(f"{section}/{item['ref']}: {name} → неизвестный {ref!r}")
    for name, target in SETTINGS_REFS.items():
        value = (bundle.get("settings") or {}).get(name)
        if value is not None and value not in known[target]:
            problems.append(f"settings: {name} → неизвестный {value!r}")
    if problems:
        raise BundleError(problems)


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class _Keys:
    """Естественные ключи кирпичей сборки: (раздел, ref) → строка-ключ."""

    def __init__(self, bundle: Bundle) -> None:
        self.bundle = bundle
        self.by_ref = {s: {i["ref"]: i for i in _items(bundle, s)} for s in SECTIONS}
        self.cache: dict[tuple[str, str], str] = {}

    def resolve(self, section: str, item: Mapping[str, Any]) -> dict[str, Any]:
        """Содержимое без `ref`, ссылки заменены ключами целей."""
        result = {k: v for k, v in item.items() if k != "ref"}
        for name, target in REFS.get(section, {}).items():
            value = item.get(name)
            if isinstance(value, list):
                result[name] = sorted(self.key(target, r) for r in value)
            elif value is not None:
                result[name] = self.key(target, value)
        return result

    def key(self, section: str, ref: str) -> str:
        cached = self.cache.get((section, ref))
        if cached is not None:
            return cached
        item = self.by_ref[section][ref]
        content = self.resolve(section, item)
        fields = NATURAL[section]
        key = _canon(content if fields is None else [content.get(f) for f in fields])
        self.cache[(section, ref)] = key
        return key


def title(section: str, item: Mapping[str, Any]) -> str:
    """Подпись кирпича для человека: название или ref."""
    for name in ("name", "title_template", "title"):
        if item.get(name):
            return str(item[name])
    return str(item["ref"])


@dataclass(frozen=True)
class ItemDiff:
    section: str
    ref: str  # ref во входящей сборке
    status: Status
    existing: str | None = None  # ref совпавшего кирпича в текущей конфигурации
    fields: tuple[str, ...] = ()  # changed: какие поля различаются
    name: str = ""


@dataclass
class BundleDiff:
    items: list[ItemDiff] = field(default_factory=list)

    def of(self, status: Status) -> list[ItemDiff]:
        return [i for i in self.items if i.status == status]

    @property
    def unchanged(self) -> bool:
        return all(i.status == "skipped" for i in self.items)


def diff(current: Bundle, incoming: Bundle) -> BundleDiff:
    """Что импорт `incoming` поверх `current` добавит, изменит и пропустит.

    Совпадение — по естественному ключу; при нескольких кандидатах берётся первый
    ещё не занятый. Ничего не удаляется: кирпичи `current`, которых нет в
    `incoming`, остаются как есть."""
    mine, theirs = _Keys(current), _Keys(incoming)
    result = BundleDiff()
    for section in SECTIONS:
        index: dict[str, list[str]] = {}
        for item in _items(current, section):
            index.setdefault(mine.key(section, item["ref"]), []).append(item["ref"])
        for item in _items(incoming, section):
            candidates = index.get(theirs.key(section, item["ref"]), [])
            name = title(section, item)
            if not candidates:
                result.items.append(ItemDiff(section, item["ref"], "added", name=name))
                continue
            existing = candidates.pop(0)
            old = mine.resolve(section, mine.by_ref[section][existing])
            new = theirs.resolve(section, item)
            changed = tuple(k for k in new if _canon(new[k]) != _canon(old.get(k)))
            status: Status = "changed" if changed else "skipped"
            result.items.append(
                ItemDiff(section, item["ref"], status, existing, changed, name=name)
            )
    return result


def settings_changes(current: Bundle, incoming: Bundle) -> list[str]:
    """Поля настроек сборки, которые импорт поменяет (ссылки — по ключам целей)."""
    mine, theirs = _Keys(current), _Keys(incoming)
    changed = []
    for name, target in SETTINGS_REFS.items():
        new = (incoming.get("settings") or {}).get(name)
        if new is None:
            continue  # не задано в сборке — не трогаем
        old = (current.get("settings") or {}).get(name)
        if old is None or mine.key(target, old) != theirs.key(target, new):
            changed.append(name)
    return changed


def unique_refs(names: Iterable[str]) -> list[str]:
    """Читаемые ref по названиям: «Смена», «Смена 2», … (повторы нумеруются)."""
    taken: set[str] = set()
    refs = []
    for name in names:
        base = " ".join(name.split())[:100] or "item"
        ref, n = base, 1
        while ref in taken:
            n += 1
            ref = f"{base} {n}"
        taken.add(ref)
        refs.append(ref)
    return refs


# ---------- черновик ИИ-настройки → сборка (M21.4) ----------

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
DEFAULT_WAKE, DEFAULT_SLEEP = "07:30", "23:30"


def _time(value: Any) -> str | None:
    m = _TIME_RE.match(str(value or "").strip())
    return f"{int(m[1]):02d}:{m[2]}" if m else None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _clamp(value: Any, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def _name(value: Any, limit: int = 100) -> str:
    return " ".join(str(value or "").split())[:limit]


WEEKDAY_NAMES = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def _weekdays(value: Any) -> list[int]:
    """Дни недели названиями («сб») или номерами ISO (6) → номера 1–7."""
    days = set()
    for d in value or []:
        if isinstance(d, str) and d.strip().lower()[:2] in WEEKDAY_NAMES:
            days.add(WEEKDAY_NAMES.index(d.strip().lower()[:2]) + 1)
        elif isinstance(d, int) and 1 <= d <= 7:
            days.add(d)
    return sorted(days)


def _minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


@dataclass
class SetupResult:
    bundle: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    about: str = ""


class _Setup:
    """Сборка из черновика: ссылки — названиями (без учёта регистра) на кирпичи
    черновика или текущей настройки; кирпич текущей настройки, на который сослались,
    копируется в сборку (при импорте он «уже есть»)."""

    def __init__(self, current: Bundle, today: date) -> None:
        self.current = current
        self.today = today
        self.out: dict[str, list[dict[str, Any]]] = {s: [] for s in SECTIONS}
        self.warnings: list[str] = []
        self.by_name: dict[str, dict[str, str]] = {s: {} for s in SECTIONS}

    def add(self, section: str, item: dict[str, Any], name: str) -> str | None:
        key = name.casefold()
        if not name or key in self.by_name[section]:
            return None
        refs = {i["ref"] for i in self.out[section]}
        ref = unique_refs([*sorted(refs), name])[-1]
        item = {"ref": ref, **item}
        self.out[section].append(item)
        self.by_name[section][key] = ref
        return ref

    def find(self, section: str, name: str) -> str | None:
        """ref кирпича по названию: из черновика или скопированный из текущей настройки."""
        name = _name(name)
        if not name:
            return None
        if ref := self.by_name[section].get(name.casefold()):
            return ref
        for item in _items(self.current, section):
            if title(section, item).casefold() == name.casefold():
                return self.borrow(section, item)
        return None

    def only_area_of(self, type_name: Any) -> str | None:
        """Модель вместо сферы назвала её тип («Работа»): единственная сфера типа."""
        type_ref = self.by_name["area_types"].get(_name(type_name).casefold())
        areas = [a["ref"] for a in self.out["areas"] if a["area_type"] == type_ref]
        return areas[0] if type_ref and len(areas) == 1 else None

    def borrow(self, section: str, item: Mapping[str, Any]) -> str | None:
        copy = dict(item)
        for field_name, target in REFS.get(section, {}).items():
            value = copy.get(field_name)
            targets = {i["ref"]: i for i in _items(self.current, target)}
            if isinstance(value, list):
                copy[field_name] = [
                    r for v in value if v in targets and (r := self.borrow(target, targets[v]))
                ]
            elif value is not None:
                copy[field_name] = self.borrow(target, targets[value]) if value in targets else None
        copy.pop("ref")
        name = title(section, item)
        if ref := self.by_name[section].get(name.casefold()):
            return ref
        return self.add(section, copy, name)


def normalize_setup(draft: Mapping[str, Any], current: Bundle, today: date) -> SetupResult:
    """Черновик ИИ-настройки (`ai/schemas.AISetup`) → `ConfigBundle`-словарь.

    Разумные границы: дорога 0–240 мин, напоминание 0–1440, лимит 15–1440 мин;
    время ЧЧ:ММ; правило без типа занятости, без дней или с пустым интервалом
    отбрасывается; повторы — тоже. Пересечения правил в один день — предупреждение.
    """
    s = _Setup(current, today)
    warn = s.warnings.append

    for t in draft.get("area_types") or []:
        name = _name(t.get("name"))
        fields = []
        for label in dict.fromkeys(_name(f, 60) for f in t.get("fields") or []):
            if label:
                fields.append({"id": None, "label": label, "type": "text"})
        s.add(
            "area_types",
            {
                "name": name,
                "name_plural": _name(t.get("name_plural")) or name,
                "fields": fields[:10],
                "sections": ["schedule", "tasks", "notes"],
            },
            name,
        )

    for a in draft.get("areas") or []:
        name = _name(a.get("name"), 200)
        type_ref = s.find("area_types", a.get("type"))
        if type_ref is None and len(s.out["area_types"]) == 1:
            type_ref = s.out["area_types"][0]["ref"]
        if type_ref is None:
            if name:
                warn(f"Сфера «{name}» без типа — пропущена")
            continue
        s.add("areas", {"area_type": type_ref, "name": name}, name)

    for e in draft.get("event_types") or []:
        name = _name(e.get("name"))
        travel = _clamp(e.get("travel_min"), 0, 240)
        remind = _clamp(e.get("remind_min"), 0, 1440)
        s.add(
            "event_types",
            {
                "name": name,
                "name_plural": _name(e.get("name_plural")) or name,
                "buffer_before_min": travel,
                "buffer_after_min": travel,
                "remind_before_min": remind or None,
                "is_rest": bool(e.get("is_rest")),
                "show_now_next": bool(e.get("show_now_next")),
            },
            name,
        )

    seen_rules: set[str] = set()
    weekly: list[tuple[str, set[int], int, int]] = []
    for r in draft.get("rules") or []:
        type_ref = s.find("event_types", r.get("event_type"))
        label = _name(r.get("title")) or _name(r.get("area")) or _name(r.get("event_type"))
        if type_ref is None:
            warn(f"«{label}»: нет типа занятости — правило пропущено")
            continue
        start, end = _time(r.get("start")), _time(r.get("end"))
        if start is None or end is None or start == end:
            warn(f"«{label}»: непонятное время — правило пропущено")
            continue
        kind = r.get("pattern")
        pattern: dict[str, Any]
        if kind == "shifts":
            on, off = _clamp(r.get("on_days"), 1, 365), _clamp(r.get("off_days"), 0, 365)
            anchor = _date(r.get("anchor"))
            if anchor is None:
                anchor = today
                warn(f"«{label}»: дата первой смены не указана — поставил сегодня, поправьте")
            pattern = {"kind": "day_cycle", "on": on, "off": off, "anchor": anchor.isoformat()}
        elif kind == "once":
            day = _date(r.get("date"))
            if day is None:
                warn(f"«{label}»: нет даты — пропущено")
                continue
            pattern = {"kind": "once", "date": day.isoformat()}
        else:
            days = _weekdays(r.get("weekdays"))
            if not days:
                warn(f"«{label}»: не указаны дни недели — пропущено")
                continue
            pattern = {"kind": "weekly", "weekdays": days, "cycle_weeks": None}
        area_ref = s.find("areas", r.get("area")) or s.only_area_of(r.get("area"))
        if _name(r.get("area")) and area_ref is None:
            warn(f"«{label}»: сферы «{_name(r.get('area'))}» нет — правило без сферы")
        item = {
            "event_type": type_ref,
            "area": area_ref,
            "pattern": pattern,
            "start_time": start,
            "end_time": end,
            "title": _name(r.get("title"), 300) or None,
        }
        signature = _canon(item)
        if signature in seen_rules:
            continue
        seen_rules.add(signature)
        s.add("schedule_rules", item, f"{label} {len(s.out['schedule_rules']) + 1}")
        if pattern["kind"] == "weekly":
            a, b = _minutes(start), _minutes(end)
            if b <= a:
                b += 24 * 60
            for other, other_days, oa, ob in weekly:
                if other_days & set(pattern["weekdays"]) and a < ob and oa < b:
                    warn(f"«{label}» и «{other}» пересекаются по времени")
            weekly.append((label, set(pattern["weekdays"]), a, b))

    for p in draft.get("day_profiles") or []:
        name = _name(p.get("name"))
        wake = _time(p.get("wake")) or DEFAULT_WAKE
        sleep = _time(p.get("sleep")) or DEFAULT_SLEEP
        work_start, work_end = _time(p.get("work_start")), _time(p.get("work_end"))
        window = (
            {"start": work_start, "end": work_end}
            if work_start and work_end and work_start != work_end
            else {"start": wake, "end": sleep}
            if wake != sleep
            else None
        )
        profile_ref = s.add(
            "day_profiles",
            {
                "name": name,
                "wake": wake,
                "sleep": sleep,
                "work_windows": [window] if window else [],
            },
            name,
        )
        if profile_ref is None:
            continue
        if days := _weekdays(p.get("weekdays")):
            rule = {"profile": profile_ref, "kind": "weekdays", "weekdays": days}
            s.add("day_profile_rules", rule, f"{name}: weekdays")
        for field_name, kind in (("on_event_type", "event_day"), ("after_event_type", "day_after")):
            if not _name(p.get(field_name)):
                continue
            type_ref = s.find("event_types", p.get(field_name))
            if type_ref is None:
                warn(f"«{name}»: нет типа занятости «{_name(p.get(field_name))}»")
                continue
            rule = {"profile": profile_ref, "kind": kind, "event_type": type_ref}
            s.add("day_profile_rules", rule, f"{name}: {kind}")

    for b in draft.get("budgets") or []:
        name = _name(b.get("name"))
        event_types = [r for n in b.get("event_types") or [] if (r := s.find("event_types", n))]
        action_types = [r for n in b.get("action_types") or [] if (r := s.find("action_types", n))]
        s.add(
            "budgets",
            {
                "name": name,
                "minutes_per_day": _clamp(b.get("minutes_per_day"), 15, 1440),
                "event_types": sorted(set(event_types)),
                "action_types": sorted(set(action_types)),
            },
            name,
        )

    for t in draft.get("task_types") or []:
        name = _name(t.get("name"))
        synonyms = [w for w in dict.fromkeys(_name(x, 60) for x in t.get("synonyms") or []) if w]
        s.add("task_types", {"name": name, "synonyms": synonyms[:30]}, name)

    bundle: dict[str, Any] = {"version": 1, **{k: v for k, v in s.out.items() if v}}
    if warning := _name(draft.get("warning"), 500):
        s.warnings.insert(0, warning)
    return SetupResult(bundle, s.warnings, _name(draft.get("about"), 1000))

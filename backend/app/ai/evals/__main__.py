"""Эталонные задания для ручной оценки промптов (M10.1, M21.2).

    cd backend && uv run python -m app.ai.evals            # всё
    uv run python -m app.ai.evals breakdown --only essay-monsoon
    uv run python -m app.ai.evals parse --profile tutor   # только кейсы репетитора
    uv run python -m app.ai.evals parse --model qwen2.5:7b-instruct --out /tmp/report.md
    uv run python -m app.ai.evals milestones          # этапы проекта (M13.2)
    uv run python -m app.ai.evals setup               # ИИ-настройка по описанию (M21.4)
    uv run python -m app.ai.evals --fallback          # запасной провайдер (LLM_FALLBACK_*)

Кейсы привязаны к профилям (`profiles.json`): студентка Part 1, репетитор, смены,
офис, школьник — «о себе» и справочники, как у такого пользователя. Без поля
`profile` кейс — студенческий. Итог печатается по профилям: студенческие сравниваются
с Part 1, новые должны проходить ≥ 80 %.

Провайдер и модели — из `.env` (`--model` переопределяет текстовую модель).
Автопроверки грубые (число шагов, сумма, ключевые слова, поля карточки) —
это подсказка, на что смотреть; качество шагов оценивается глазами по отчёту.
"""

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from typing import Any

from app.ai import LLMError, build_provider
from app.ai.prompts import (
    AreaHint,
    BreakdownContext,
    ExistingMilestone,
    Hint,
    MilestonesContext,
    ParseContext,
    Profile,
    SetupContext,
    breakdown_messages,
    milestones_messages,
    parse_messages,
    setup_messages,
)
from app.ai.provider import ChatProvider, FallbackProvider, LLMProvider
from app.ai.schemas import AIBreakdown, AIMilestones, AIParsed, AISetup, with_choices
from app.domain.breakdown import RawStep, fmt_minutes, normalize_steps, time_warning
from app.domain.bundle import check_refs, normalize_setup
from app.domain.projects import RawMilestone, normalize_milestones

HERE = Path(__file__).parent
STUDENT = "student"


@dataclass(frozen=True)
class EvalProfile:
    key: str
    profile: Profile
    # Название типа действия «связь с людьми» — для проверки people_step
    people: str

    def choices(self) -> dict[str, list[str]]:
        p = self.profile
        return {
            "area": p.area_names,
            "task_type": p.task_type_names,
            "action_type": p.action_type_names,
            "category": list(p.categories),
        }


def load_profiles() -> dict[str, EvalProfile]:
    raw = json.loads((HERE / "profiles.json").read_text())
    result = {}
    for key, p in raw.items():
        profile = Profile(
            about=p["about"],
            areas=[AreaHint(a["name"], a.get("kind", "")) for a in p["areas"]],
            task_types=[Hint(t["name"], tuple(t["synonyms"])) for t in p["task_types"]],
            action_types=[Hint(t["name"], tuple(t["synonyms"])) for t in p["action_types"]],
            categories=p["categories"],
        )
        result[key] = EvalProfile(key, profile, p["people"])
    return result


PROFILES = load_profiles()


@dataclass
class Case:
    id: str
    ok: bool
    seconds: float
    report: list[str]
    failures: list[str] = field(default_factory=list)
    profile: str = STUDENT


def _in(value: int, bounds: list[int]) -> bool:
    return bounds[0] <= value <= bounds[1]


async def breakdown_case(provider: LLMProvider, raw: dict[str, Any]) -> Case:
    ep = PROFILES[raw.get("profile", STUDENT)]
    today = date.today()
    deadline = datetime.combine(today + timedelta(days=raw["deadline_days"]), dtime(23, 59))
    area = next((a for a in ep.profile.areas if a.name == raw.get("area")), None)
    ctx = BreakdownContext(
        title=raw["title"],
        today=today,
        task_type=raw.get("task_type"),
        description=raw.get("description", ""),
        area=f"{area.name} ({area.kind})" if area else raw.get("area"),
        project=raw.get("project"),
        deadline=deadline,
        free_minutes=raw.get("free_minutes"),
        profile=ep.profile,
    )
    started = time.monotonic()
    try:
        completion = await provider.complete_json(
            breakdown_messages(ctx), with_choices(AIBreakdown, **ep.choices())
        )
    except LLMError as exc:
        return Case(raw["id"], False, time.monotonic() - started, [], [exc.message], ep.key)
    seconds = time.monotonic() - started
    answer = completion.value
    draft = normalize_steps(
        [
            RawStep(s.order, s.title, s.estimate_min, s.action_type, tuple(s.depends_on), s.note)
            for s in answer.subtasks
        ]
    )
    expect = raw.get("expect", {})
    failures = []
    if "steps" in expect and not _in(len(draft.steps), expect["steps"]):
        failures.append(f"шагов {len(draft.steps)}, ждали {expect['steps']}")
    if "total" in expect and not _in(draft.total_estimate_min, expect["total"]):
        failures.append(f"сумма {draft.total_estimate_min} мин, ждали {expect['total']}")
    text = " ".join(f"{s.title} {s.note}" for s in draft.steps).lower()
    for word in expect.get("keywords", []):
        if word.lower() not in text:
            failures.append(f"нет «{word}»")
    warning = answer.warning or time_warning(draft.total_estimate_min, raw.get("free_minutes"))
    if expect.get("warning") and not warning:
        failures.append("нет предупреждения о нехватке времени")
    if expect.get("people_step") and not any(s.action_type == ep.people for s in draft.steps):
        failures.append("нет шага «связь с людьми»")
    if len(completion.attempts) > 1:
        failures.append("понадобился повтор")

    report = [f"тип: {answer.task_type}, категория: {answer.category}"]
    for i, s in enumerate(draft.steps, 1):
        deps = f" ← {', '.join(str(d + 1) for d in s.depends_on)}" if s.depends_on else ""
        note = f" — _{s.note}_" if s.note else ""
        report.append(f"{i}. {s.title} · {s.estimate_min} мин · {s.action_type}{deps}{note}")
    report.append(f"итого {fmt_minutes(draft.total_estimate_min)}")
    if answer.warning:
        report.append(f"⚠️ ИИ: {answer.warning}")
    if warning and warning != answer.warning:
        report.append(f"⚠️ расчёт: {warning}")
    return Case(raw["id"], not failures, seconds, report, failures, ep.key)


async def parse_case(provider: LLMProvider, raw: dict[str, Any], now: datetime) -> Case:
    ep = PROFILES[raw.get("profile", STUDENT)]
    started = time.monotonic()
    try:
        completion = await provider.complete_json(
            parse_messages(ParseContext(raw["text"], now, ep.profile)),
            with_choices(AIParsed, **ep.choices()),
        )
    except LLMError as exc:
        return Case(raw["text"][:40], False, time.monotonic() - started, [], [exc.message], ep.key)
    seconds = time.monotonic() - started
    got = completion.value.model_dump(mode="json")
    failures = [
        f"{key}: {got.get(key)!r}, ждали {value!r}"
        for key, value in raw["expect"].items()
        if got.get(key) != value
    ]
    report = [
        f"«{raw['text']}»",
        f"→ {got['kind']} · «{got['title']}» · {got.get('task_type')} · {got.get('area')} · "
        f"{got.get('deadline_date')} {got.get('deadline_time') or ''}",
    ]
    if got.get("description"):
        report.append(f"описание: {got['description']}")
    return Case(raw["text"][:40], not failures, seconds, report, failures, ep.key)


async def milestones_case(provider: LLMProvider, raw: dict[str, Any], today: date) -> Case:
    ep = PROFILES[raw.get("profile", STUDENT)]
    deadline = date.fromisoformat(raw["deadline"]) if raw.get("deadline") else None
    existing = [
        ExistingMilestone(m["title"], date.fromisoformat(m["date"]), m["done"])
        for m in raw.get("existing", [])
    ]
    ctx = MilestonesContext(
        title=raw["title"],
        today=today,
        description=raw.get("description", ""),
        deadline=deadline,
        weekly_norm_min=raw.get("weekly_norm_min"),
        existing=existing,
        pauses=raw.get("pauses", []),
        profile=ep.profile,
    )
    started = time.monotonic()
    try:
        completion = await provider.complete_json(milestones_messages(ctx), AIMilestones)
    except LLMError as exc:
        return Case(raw["id"], False, time.monotonic() - started, [], [exc.message], ep.key)
    seconds = time.monotonic() - started
    answer = completion.value
    items = normalize_milestones(
        (RawMilestone(m.title, m.date, m.note) for m in answer.milestones),
        today=today,
        deadline=deadline,
        existing=[m.title for m in existing],
    )
    expect = raw.get("expect", {})
    failures = []
    if "count" in expect and not _in(len(items), expect["count"]):
        failures.append(f"этапов {len(items)}, ждали {expect['count']}")
    text = " ".join(f"{m.title} {m.note}" for m in items).lower()
    for word in expect.get("keywords", []):
        if word.lower() not in text:
            failures.append(f"нет «{word}»")
    raw_titles = [m.title for m in answer.milestones]
    for title in expect.get("skip", []):
        if title in raw_titles:
            failures.append(f"повторил существующий этап «{title}»")
    raw_dates = [m.date for m in answer.milestones if m.date]
    if raw_dates != sorted(raw_dates):
        failures.append("даты не по порядку")
    if deadline and any(d > deadline or d < today for d in raw_dates):
        failures.append("даты вне [сегодня, итоговый срок]")
    if sum(m.date is None for m in answer.milestones):
        failures.append("есть этапы без даты")
    if expect.get("warning") and not answer.warning:
        failures.append("нет warning (просили указать срок)")
    if len(completion.attempts) > 1:
        failures.append("понадобился повтор")

    report = [f"{i}. {m.date or '—'} · {m.title}" + (f" — _{m.note}_" if m.note else "")
              for i, m in enumerate(items, 1)]  # fmt: skip
    if answer.warning:
        report.append(f"⚠️ ИИ: {answer.warning}")
    return Case(raw["id"], not failures, seconds, report, failures, ep.key)


# Нулевая настройка: засеянные типы действий и режимы «Будни» / «Выходные»
ZERO_CONFIG: dict[str, Any] = {
    "version": 1,
    "action_types": [
        {"ref": t.name, "name": t.name, "windows": [], "category": None, "synonyms": []}
        for t in PROFILES["office"].profile.action_types
    ],
    "day_profiles": [
        {"ref": "Будни", "name": "Будни", "wake": "07:30", "sleep": "23:30"},
        {"ref": "Выходные", "name": "Выходные", "wake": "09:00", "sleep": "00:30"},
    ],
}


def _rule_matches(rule: dict[str, Any], want: dict[str, Any]) -> bool:
    pattern = rule["pattern"]
    checks = {
        "pattern": pattern["kind"],
        "on": pattern.get("on"),
        "off": pattern.get("off"),
        "weekdays": pattern.get("weekdays"),
        "start": rule["start_time"],
        "end": rule["end_time"],
    }
    return all(checks[k] == v for k, v in want.items())


async def setup_case(provider: LLMProvider, raw: dict[str, Any], today: date) -> Case:
    ctx = SetupContext(
        raw["text"],
        today,
        existing={
            "action_types": [t["name"] for t in ZERO_CONFIG["action_types"]],
            "day_profiles": ["Будни", "Выходные"],
        },
    )
    started = time.monotonic()
    try:
        completion = await provider.complete_json(setup_messages(ctx), AISetup)
    except LLMError as exc:
        return Case(raw["id"], False, time.monotonic() - started, [], [exc.message], "setup")
    seconds = time.monotonic() - started
    result = normalize_setup(completion.value.model_dump(mode="json"), ZERO_CONFIG, today)
    b = result.bundle
    failures = []
    try:
        check_refs(b)
    except ValueError as exc:
        failures.append(f"ссылки: {exc}")
    rules = b.get("schedule_rules", [])
    expect = raw["expect"]
    for want in expect.get("rules", []):
        if not any(_rule_matches(r, want) for r in rules):
            failures.append(f"нет правила {want}")
    if len(b.get("areas", [])) < expect.get("min_areas", 0):
        failures.append(f"сфер {len(b.get('areas', []))}, ждали ≥ {expect['min_areas']}")
    if len(b.get("event_types", [])) < expect.get("min_event_types", 0):
        failures.append(f"типов занятости меньше {expect['min_event_types']}")
    if "budget_minutes" in expect and not any(
        x["minutes_per_day"] == expect["budget_minutes"] for x in b.get("budgets", [])
    ):
        failures.append(f"нет лимита {expect['budget_minutes']} мин")
    if "buffer" in expect and not any(
        t.get("buffer_before_min") == expect["buffer"] for t in b.get("event_types", [])
    ):
        failures.append(f"нет дороги {expect['buffer']} мин")
    if expect.get("day_after") and not any(
        r["kind"] == "day_after" for r in b.get("day_profile_rules", [])
    ):
        failures.append("нет режима «после» события")
    if len(completion.attempts) > 1:
        failures.append("понадобился повтор")

    report = [f"«{raw['text']}»", f"о себе: {result.about}"]
    for section in ("area_types", "areas", "event_types", "day_profiles", "budgets", "task_types"):
        if b.get(section):
            report.append(f"{section}: " + ", ".join(i["ref"] for i in b[section]))
    for r in rules:
        p = r["pattern"]
        when = p.get("weekdays") or f"{p.get('on')}/{p.get('off')} c {p.get('anchor')}"
        report.append(
            f"- {r['event_type']} · {r.get('area') or '—'} · {p['kind']} {when} · "
            f"{r['start_time']}–{r['end_time']}"
        )
    for w in result.warnings:
        report.append(f"⚠️ {w}")
    return Case(raw["id"], not failures, seconds, report, failures, "setup")


def _print(title: str, cases: list[Case]) -> list[str]:
    lines = [f"## {title}", ""]
    for c in cases:
        mark = "✅" if c.ok else "❌"
        lines.append(f"### {mark} [{c.profile}] {c.id} ({c.seconds:.1f} с)")
        lines.extend(c.report)
        lines.extend(f"- ❗ {f}" for f in c.failures)
        lines.append("")
    passed = sum(c.ok for c in cases)
    avg = sum(c.seconds for c in cases) / max(1, len(cases))
    lines.append(f"**{passed}/{len(cases)} прошли автопроверки, в среднем {avg:.1f} с**")
    lines.append("")
    return lines


def _summary(cases: list[Case]) -> list[str]:
    """Итог по профилям: студенческие — сравнить с Part 1, новые — ≥ 80 %."""
    lines = ["## Итог по профилям", ""]
    for key in PROFILES:
        mine = [c for c in cases if c.profile == key]
        if mine:
            passed = sum(c.ok for c in mine)
            lines.append(f"- {key}: {passed}/{len(mine)} ({100 * passed // len(mine)} %)")
    setup = [c for c in cases if c.profile == "setup"]
    if setup:
        passed = sum(c.ok for c in setup)
        lines.append(f"- setup: {passed}/{len(setup)} ({100 * passed // len(setup)} %)")
    new = [c for c in cases if c.profile not in (STUDENT, "setup")]
    if new:
        passed = sum(c.ok for c in new)
        lines.append(f"- **новые профили: {passed}/{len(new)} ({100 * passed // len(new)} %)**")
    lines.append("")
    return lines


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "suite",
        nargs="?",
        choices=["breakdown", "parse", "milestones", "setup", "all"],
        default="all",
    )
    parser.add_argument("--model", help="Текстовая модель вместо LLM_MODEL")
    parser.add_argument("--only", help="id задания разбивки или проекта")
    parser.add_argument("--profile", choices=list(PROFILES), help="Только кейсы профиля")
    parser.add_argument("--fallback", action="store_true", help="Оценить запасной провайдер")
    parser.add_argument("--out", type=Path, help="Сохранить отчёт в Markdown")
    args = parser.parse_args()

    provider = build_provider()
    # С запасным провайдером оцениваем один из них: по умолчанию основной
    if isinstance(provider, FallbackProvider):
        provider = provider.fallback if args.fallback else provider.primary
    elif args.fallback:
        parser.error("LLM_FALLBACK_PROVIDER не задан")
    if args.model and isinstance(provider, ChatProvider):
        provider.model = args.model
    model = getattr(provider, "model", "?")
    lines = [f"# Evals: {provider.name} / {model}", ""]

    def mine(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if args.only:
            items = [t for t in items if t.get("id") == args.only]
        if args.profile:
            items = [t for t in items if t.get("profile", STUDENT) == args.profile]
        return items

    everything: list[Case] = []
    if args.suite in ("breakdown", "all"):
        tasks = mine(json.loads((HERE / "breakdown.json").read_text()))
        cases = [await breakdown_case(provider, t) for t in tasks]
        lines += _print("Разбивка", cases)
        everything += cases

    if args.suite in ("parse", "all"):
        data = json.loads((HERE / "parse.json").read_text())
        now = datetime.combine(
            date.fromisoformat(data["today"]), dtime.fromisoformat(data["now_time"])
        )
        cases = [await parse_case(provider, c, now) for c in mine(data["cases"])]
        lines += _print("Разбор текста", cases)
        everything += cases

    if args.suite in ("milestones", "all"):
        data = json.loads((HERE / "milestones.json").read_text())
        today = date.fromisoformat(data["today"])
        cases = [await milestones_case(provider, p, today) for p in mine(data["cases"])]
        lines += _print("Этапы проекта", cases)
        everything += cases

    if args.suite in ("setup", "all"):
        data = json.loads((HERE / "setup.json").read_text())
        today = date.fromisoformat(data["today"])
        raw = [c for c in data["cases"] if not args.only or c["id"] == args.only]
        cases = [await setup_case(provider, c, today) for c in raw]
        lines += _print("ИИ-настройка", cases)
        everything += cases

    lines += _summary(everything)

    text = "\n".join(lines)
    print(text)
    if args.out:
        args.out.write_text(text)


if __name__ == "__main__":
    asyncio.run(main())

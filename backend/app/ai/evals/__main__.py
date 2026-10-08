"""Эталонные задания для ручной оценки промптов (M10.1).

    cd backend && uv run python -m app.ai.evals            # всё
    uv run python -m app.ai.evals breakdown --only essay-monsoon
    uv run python -m app.ai.evals parse --model qwen2.5:7b-instruct --out /tmp/report.md
    uv run python -m app.ai.evals --fallback          # запасной провайдер (LLM_FALLBACK_*)

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
from app.ai.prompts import BreakdownContext, ParseContext, breakdown_messages, parse_messages
from app.ai.provider import ChatProvider, FallbackProvider, LLMProvider
from app.ai.schemas import AIBreakdown, AIParsed, with_subjects
from app.domain.breakdown import RawStep, fmt_minutes, normalize_steps, time_warning

HERE = Path(__file__).parent


@dataclass
class Case:
    id: str
    ok: bool
    seconds: float
    report: list[str]
    failures: list[str] = field(default_factory=list)


def _in(value: int, bounds: list[int]) -> bool:
    return bounds[0] <= value <= bounds[1]


async def breakdown_case(provider: LLMProvider, raw: dict[str, Any]) -> Case:
    today = date.today()
    deadline = datetime.combine(today + timedelta(days=raw["deadline_days"]), dtime(23, 59))
    ctx = BreakdownContext(
        title=raw["title"],
        today=today,
        task_type=raw.get("task_type") if raw.get("task_type") != "other" else None,
        description=raw.get("description", ""),
        subject=raw.get("subject"),
        project=raw.get("project"),
        deadline=deadline,
        free_minutes=raw.get("free_minutes"),
    )
    started = time.monotonic()
    try:
        completion = await provider.complete_json(breakdown_messages(ctx), AIBreakdown)
    except LLMError as exc:
        return Case(raw["id"], False, time.monotonic() - started, [], [exc.message])
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
    if expect.get("people_step") and not any(s.action_type == "people" for s in draft.steps):
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
    return Case(raw["id"], not failures, seconds, report, failures)


async def parse_case(
    provider: LLMProvider, raw: dict[str, Any], now: datetime, subjects: list[str]
) -> Case:
    started = time.monotonic()
    try:
        completion = await provider.complete_json(
            parse_messages(ParseContext(raw["text"], now, subjects)),
            with_subjects(AIParsed, subjects),
        )
    except LLMError as exc:
        return Case(raw["text"][:40], False, time.monotonic() - started, [], [exc.message])
    seconds = time.monotonic() - started
    got = completion.value.model_dump(mode="json")
    failures = [
        f"{key}: {got.get(key)!r}, ждали {value!r}"
        for key, value in raw["expect"].items()
        if got.get(key) != value
    ]
    report = [
        f"«{raw['text']}»",
        f"→ {got['kind']} · «{got['title']}» · {got.get('task_type')} · {got.get('subject')} · "
        f"{got.get('deadline_date')} {got.get('deadline_time') or ''}",
    ]
    if got.get("description"):
        report.append(f"описание: {got['description']}")
    return Case(raw["text"][:40], not failures, seconds, report, failures)


def _print(title: str, cases: list[Case]) -> list[str]:
    lines = [f"## {title}", ""]
    for c in cases:
        mark = "✅" if c.ok else "❌"
        lines.append(f"### {mark} {c.id} ({c.seconds:.1f} с)")
        lines.extend(c.report)
        lines.extend(f"- ❗ {f}" for f in c.failures)
        lines.append("")
    passed = sum(c.ok for c in cases)
    avg = sum(c.seconds for c in cases) / max(1, len(cases))
    lines.append(f"**{passed}/{len(cases)} прошли автопроверки, в среднем {avg:.1f} с**")
    lines.append("")
    return lines


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", nargs="?", choices=["breakdown", "parse", "all"], default="all")
    parser.add_argument("--model", help="Текстовая модель вместо LLM_MODEL")
    parser.add_argument("--only", help="id задания разбивки")
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

    if args.suite in ("breakdown", "all"):
        tasks = json.loads((HERE / "breakdown.json").read_text())
        if args.only:
            tasks = [t for t in tasks if t["id"] == args.only]
        cases = [await breakdown_case(provider, t) for t in tasks]
        lines += _print("Разбивка", cases)

    if args.suite in ("parse", "all"):
        data = json.loads((HERE / "parse.json").read_text())
        now = datetime.combine(
            date.fromisoformat(data["today"]), dtime.fromisoformat(data["now_time"])
        )
        cases = [await parse_case(provider, c, now, data["subjects"]) for c in data["cases"]]
        lines += _print("Разбор текста", cases)

    text = "\n".join(lines)
    print(text)
    if args.out:
        args.out.write_text(text)


if __name__ == "__main__":
    asyncio.run(main())

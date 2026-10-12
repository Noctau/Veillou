"""Характеризационные тесты (M14.1): поведение Part 1 на данных студентки.

Снимки в tests/snapshots/student/ должны оставаться зелёными после каждой вехи
Part 2 (M15–M20). Меняется снимок — только осознанно, с пометкой в коммите.

- calendar.txt — вхождения календаря на 4 недели (после применения плана);
- plan_input.json / plan_result.json — нормализованный вход и итог жадного движка;
- digest.txt, week.txt — утренняя сводка и недельный вид (/week);
- reminders.txt — будущие напоминания с dedupe_key и их тексты;
- quickparse.txt — быстрый ввод на 25 фразах из test_quickparse.py.
"""

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.db import session_factory
from app.core.time import wall_to_utc
from app.domain.enums import ReminderKind, ReminderStatus
from app.domain.planner import PlanInput, PlanResult, solve
from app.models import Reminder, User
from app.services.digest import Digest
from app.services.notify_render import render
from app.services.reminders import sync_user_reminders
from app.services.replan import ReplanService

from .snapshot_utils import Labels, Snapshots
from .student import API, NOW, TODAY, TZ, Clock, build_student

pytestmark = pytest.mark.snapshots

WEEKS = 4
# «Сейчас» test_quickparse.py — вторник 06.10.2026 15:00 МСК
QUICKPARSE_NOW = datetime(2026, 10, 6, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))
PHRASES = [
    "реферат климатология до 15 окт",
    "доклад по физике атмосферы к пятнице",
    "дз по матану через 2 недели",
    "прочитать главу 3 учебника по климатологии к 12.10",
    "лаба по физат 20.10",
    "сдать курсовую 1 декабря",
    "подготовиться к экзамену по климатологии до 20 января",
    "зачёт по англу 15.10.2026",
    "сделать презентацию к докладу послезавтра",
    "решить задачи к 18:00",
    "отчёт для работы до конца месяца",
    "написать научруку до пятницы",
    "лабораторная по физат, срок 30 октября",
    "сдать реферат",
    "завтра в 14 консультация по динмету",
    "встреча с научруком в четверг в 15:30",
    "бассейн с 19 до 20:30",
    "врач в 9 утра",
    "в 7 вечера кино",
    "позвонить маме через 2 часа",
    "консультация 12/10 в 11:00",
    "записаться к стоматологу",
    "разобрать шкаф на следующей неделе",
    "через неделю вернуть книгу в библиотеку",
    "убраться дома в субботу на 2 часа",
]
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
# Поля события, которые не печатаем отдельно (время — в строке, id — в метке)
EVENT_SKIP = {"id", "start", "end", "kind", "title"}


# ---------- форматирование ----------


def calendar_text(data: dict, labels: Labels) -> str:
    out: list[str] = []
    for d in data["days_off"]:
        out.append(f"выходной {d['date_from']}…{d['date_to']} {d['title']}")
    by_day: dict[date, list[dict]] = {}
    for e in data["events"]:
        start = datetime.fromisoformat(e["start"])
        by_day.setdefault(start.astimezone(TZ).date(), []).append(e)
    for d in sorted(by_day):
        out.append(f"\n== {WEEKDAYS[d.weekday()]} {d.isoformat()} ==")
        events = sorted(by_day[d], key=lambda e: (e["start"], e["end"], e["title"], e["kind"]))
        for e in events:
            start, end = (datetime.fromisoformat(e[k]).astimezone(TZ) for k in ("start", "end"))
            span = f"{start:%H:%M}–{end:%H:%M}"
            if end.date() != start.date():
                span += f" ({end:%d.%m})"
            extra = [
                f"{k}={labels.inline(v)}"
                for k, v in sorted(e.items())
                if k not in EVENT_SKIP and v not in (None, "", False)
            ]
            out.append(f"{span} [{e['kind']}] {e['title']}  " + " ".join(extra))
    return "\n".join(out)


def plan_result_text(result: PlanResult, labels: Labels) -> str:
    stats = result.stats
    return labels.json(
        {
            "placements": sorted(
                result.placements, key=lambda p: (p.start, str(p.block_id), p.part)
            ),
            "at_risk": sorted(result.at_risk, key=lambda r: (str(r.block_id), str(r.reason))),
            "diff": {
                "added": len(result.diff.added),
                "removed": result.diff.removed,
                "moved": result.diff.moved,
            },
            "stats": {
                "engine": stats.engine,
                "status": stats.status,
                "blocks": stats.blocks,
                "placed": stats.placed,
                "split": stats.split,
                "horizon_start": stats.horizon_start,
                "horizon_end": stats.horizon_end,
            },
        }
    )


def message_text(msg) -> str:
    body = msg.plain_body()
    return f"# {msg.title}\n{body}".rstrip() + f"\n(url={msg.url})"


# ---------- снимки ----------


async def test_student_snapshots(clock: Clock, auth_client: AsyncClient, user):
    snaps = Snapshots("student")
    await build_student(auth_client)

    async def labels() -> Labels:
        result = Labels(TZ)
        async with session_factory() as db:
            await result.load(db, user.id)
        return result

    # План: нормализованный вход и итог жадного движка, затем применяем его
    async with session_factory() as db:
        u = await db.get(User, user.id)
        snap = await ReplanService(db, u, NOW).snapshot()
    inp: PlanInput = replace(snap.inp, time_limit_s=0)
    result = solve(inp)
    assert result.stats.engine == "greedy"
    lab = await labels()
    snaps.check("plan_input.json", lab.json(inp))
    snaps.check("plan_result.json", plan_result_text(result, lab))

    async with session_factory() as db:
        svc = ReplanService(db, await db.get(User, user.id), NOW)
        rev = await svc.preview(force=True)
        assert rev is not None
        await svc.apply(rev.id)

    # Календарь на 4 недели
    resp = await auth_client.get(
        f"{API}/calendar",
        params={
            "from": wall_to_utc(TODAY, time(0), TZ).isoformat(),
            "to": wall_to_utc(TODAY + timedelta(weeks=WEEKS), time(0), TZ).isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    lab = await labels()
    snaps.check("calendar.txt", calendar_text(resp.json(), lab))

    # Утренняя сводка и недельный вид
    morning = wall_to_utc(TODAY, time(8), TZ)
    async with session_factory() as db:
        u = await db.get(User, user.id)
        digest = Digest(db, u, morning)
        today = await digest.day(TODAY, morning=True)
        weeks = [await digest.week(TODAY + timedelta(weeks=i)) for i in range(2)]
    snaps.check("digest.txt", lab.text(message_text(today)))
    snaps.check("week.txt", lab.text("\n\n".join(message_text(w) for w in weeks)))

    # Будущие напоминания (8 дней) и их тексты в момент отправки
    async with session_factory() as db:
        await sync_user_reminders(db, user.id, NOW)
    async with session_factory() as db:
        u = await db.get(User, user.id)
        rows = list(
            await db.scalars(
                select(Reminder).where(
                    Reminder.user_id == user.id, Reminder.status == ReminderStatus.pending
                )
            )
        )
        lab = await labels()
        lines = []
        # В ключах UUID — порядок совпавших по времени задаём по меткам
        for r in sorted(rows, key=lambda r: (r.fire_at, lab.text(r.dedupe_key))):
            expires = lab.local(r.expires_at) if r.expires_at else "-"
            entity = f"{r.entity_type}:{r.entity_id}" if r.entity_type else "-"
            lines.append(
                f"{lab.local(r.fire_at)} {r.kind} key={r.dedupe_key}"
                f" channels={','.join(r.channels)} entity={entity} expires={expires}"
                f" payload={lab.inline(r.payload)}"
            )
            if r.kind == ReminderKind.morning_digest:
                continue  # текст сводки — в digest.txt
            clock.set(r.fire_at)
            msg = await render(db, u, r, r.fire_at)
            lines.append(
                "  " + (message_text(msg) if msg else "(нечего отправлять)").replace("\n", "\n  ")
            )
        clock.set(NOW)
    snaps.check("reminders.txt", lab.text("\n".join(lines)))

    # Быстрый ввод — на предметах студентки
    clock.set(QUICKPARSE_NOW)
    parsed = []
    for phrase in PHRASES:
        resp = await auth_client.post(f"{API}/quick-add/parse", json={"text": phrase})
        assert resp.status_code == 200, resp.text
        data = {k: v for k, v in resp.json().items() if v not in (None, False)}
        parsed.append(f"{phrase}\n  " + " ".join(f"{k}={lab.inline(v)}" for k, v in data.items()))
    snaps.check("quickparse.txt", "\n".join(parsed))

    snaps.verify()

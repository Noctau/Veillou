"""Проекты в боте: список, карточка с этапами и заданиями.

Кнопки (`m:…`):
- `pl:<стр>` — активные проекты; `p:<id>` — карточка;
- `pd:<id>` — завершить / вернуть проект; `pm:<id этапа>` — этап пройден / нет;
- `pt:<id>` — задания проекта; `ask:np:-` — новый проект; `ask:pn:<id>` — новое
  задание в проекте.
"""

import uuid

from aiogram.types import CallbackQuery, Message

from app.bot.kit import (
    Button,
    Ctx,
    Screen,
    btn,
    clip,
    esc,
    kb,
    link,
    on_callback,
    on_input,
    page_of,
    pager,
    short,
    to_int,
    uid,
)
from app.bot.tasks_ui import task_card
from app.core.exceptions import InvalidDataError
from app.core.time import get_tz, local_date, now_utc
from app.domain.breakdown import fmt_minutes
from app.domain.enums import MilestoneStatus, ProjectStatus, TaskStatus
from app.notify.message import fmt_day
from app.schemas.project import MilestoneUpdate, ProjectCreate, ProjectUpdate
from app.schemas.task import TaskCreate
from app.services import quickadd
from app.services.projects import ProjectService
from app.services.tasks import TaskService


async def project_list(ctx: Ctx, page: int = 0) -> Screen:
    projects = await ProjectService(ctx.db, ctx.user).list([ProjectStatus.active])
    shown, page = page_of(projects, page)
    text = f"<b>Проекты</b> ({len(projects)})" if projects else "<b>Проекты</b>\n\nАктивных нет."
    rows: list[list[Button]] = []
    for p in shown:
        progress = f" · {p.tasks_done}/{p.tasks_total}" if p.tasks_total else ""
        rows.append([btn(short(p.title, 36) + progress, "p", p.id)])
    rows.append(pager("pl", page, len(projects)))
    rows.append([btn("➕ Новый проект", "ask", "np", "-"), btn("☰ Меню", "menu")])
    rows.append([link("/projects")])
    return text, kb(*rows)


@on_callback("pl")
async def _pl(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await project_list(ctx, to_int(args[0] if args else None))


async def project_card(ctx: Ctx, project_id: uuid.UUID) -> Screen:
    p = await ProjectService(ctx.db, ctx.user).get_detail(project_id)
    today = local_date(now_utc(), get_tz(ctx.user.timezone))
    done = p.status == ProjectStatus.done
    lines = [f"{'✅ ' if done else ''}<b>{esc(p.title)}</b>"]
    if p.deadline:
        lines.append(f"📅 до {fmt_day(p.deadline, today)}")
    if p.tasks_total:
        lines.append(f"Заданий сделано: {p.tasks_done} из {p.tasks_total}")
    if p.weekly_norm_min:
        lines.append(
            f"Норма в неделю: {fmt_minutes(p.weekly_norm_min)}, "
            f"сделано {fmt_minutes(p.week_done_min)}"
        )
    if p.behind_days > 0:
        lines.append(f"⚠️ Отставание: {p.behind_days} дн.")
    if p.description.strip():
        lines.append(f"\n{esc(short(p.description, 300))}")
    rows: list[list[Button]] = []
    if p.milestones:
        lines.append("\n<b>Этапы</b> (нажмите, чтобы отметить):")
        for m in p.milestones[:15]:
            mark = "✓" if m.status == MilestoneStatus.done else "○"
            when = f" · {fmt_day(m.date, today)}" if m.date else ""
            rows.append([btn(f"{mark} {short(m.title, 34)}{when}", "pm", m.id)])
    rows.append([btn("📋 Задания", "pt", p.id), btn("➕ Задание", "ask", "pn", p.id)])
    rows.append(
        [
            btn("↩ Вернуть в работу" if done else "✓ Завершить проект", "pd", p.id),
            btn("← Проекты", "pl", 0),
        ]
    )
    rows.append([link(f"/projects/{p.id}")])
    return clip("\n".join(lines)), kb(*rows)


@on_callback("p")
async def _p(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    return await project_card(ctx, uid(args[0]))


@on_callback("pd")
async def _done(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    svc = ProjectService(ctx.db, ctx.user)
    p = await svc.get_detail(uid(args[0]))
    done = p.status == ProjectStatus.done
    await svc.update(
        p.id, ProjectUpdate(status=ProjectStatus.active if done else ProjectStatus.done)
    )
    ctx.say("Проект снова в работе" if done else "Проект завершён ✓")
    return await project_card(ctx, p.id)


@on_callback("pm")
async def _milestone(ctx: Ctx, callback: CallbackQuery, args: list[str]) -> Screen:
    svc = ProjectService(ctx.db, ctx.user)
    m = await svc.milestones.get_or_404(uid(args[0]))
    done = m.status == MilestoneStatus.done
    await svc.update_milestone(
        m.id, MilestoneUpdate(status=MilestoneStatus.planned if done else MilestoneStatus.done)
    )
    ctx.say("Этап снова впереди" if done else "Этап пройден ✓")
    return await project_card(ctx, m.project_id)


@on_callback("pt")
async def _tasks(ctx: Ctx, _: CallbackQuery, args: list[str]) -> Screen:
    project_id = uid(args[0])
    p = await ProjectService(ctx.db, ctx.user).get_detail(project_id)
    tasks = await TaskService(ctx.db, ctx.user).list_tasks(
        statuses=[TaskStatus.active, TaskStatus.done], project_id=project_id
    )
    tasks.sort(key=lambda t: t.status == TaskStatus.done)
    rows: list[list[Button]] = [
        [btn(f"{'✓ ' if t.status == TaskStatus.done else ''}{short(t.title, 40)}", "t", t.id)]
        for t in tasks[:30]
    ]
    rows.append([btn("➕ Задание", "ask", "pn", project_id), btn("← Проект", "p", project_id)])
    text = f"<b>{esc(p.title)}</b> — задания" + ("" if tasks else "\n\nЗаданий пока нет.")
    return text, kb(*rows)


@on_input("np", "Название проекта:")
async def _new_project(ctx: Ctx, message: Message, _: str) -> Screen:
    title = " ".join((message.text or "").split())[:300]
    if not title:
        raise InvalidDataError("Название не может быть пустым")
    p = await ProjectService(ctx.db, ctx.user).create(ProjectCreate(title=title))
    return await project_card(ctx, p.id)


@on_input("pn", "Новое задание проекта: «глава 2 до 1 ноя».")
async def _new_task(ctx: Ctx, message: Message, arg: str) -> Screen:
    project_id = uid(arg)
    p = (await quickadd.parse_text(ctx.db, ctx.user, (message.text or "")[:500])).result
    title = (p.title or message.text or "").strip()[:300]
    if not title:
        raise InvalidDataError("Напишите, что за задание")
    task = await TaskService(ctx.db, ctx.user).create(
        TaskCreate(
            title=title,
            project_id=project_id,
            deadline=p.deadline if p.date else None,
            estimate_min=min(max(p.duration_min, 5), 10_000) if p.duration_min else None,
        )
    )
    return await task_card(ctx, task.id)

"""Калибровка оценок (M9.4): коэффициент по (тип задания, тип действия).

Пересчитывается с нуля по истории отметок сделанных подзадач — так правка
или снятие отметки задним числом учитывается сама. «Сбросить» не стирает
отметки, а начинает историю заново с текущего момента (`reset_at`).
"""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import now_utc
from app.domain.calibration import coefficient
from app.domain.enums import ActionTypeKey, Feel, SubtaskStatus
from app.models import ActionType, Calibration, Subtask, Task

Key = tuple[str, str]  # (task_type, action_type key)

# Подзадача без типа действия считается самостоятельной учёбой (дефолт задания)
DEFAULT_ACTION = ActionTypeKey.study


async def _rows(db: AsyncSession, user_id: uuid.UUID) -> dict[Key, Calibration]:
    rows = await db.scalars(
        select(Calibration).where(Calibration.user_id == user_id, Calibration.deleted_at.is_(None))
    )
    return {(r.task_type, r.action_type): r for r in rows}


async def recalibrate(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Пересчитывает все коэффициенты пользователя по отметкам. Не коммитит."""
    await db.flush()
    keys = dict(
        (
            await db.execute(
                select(ActionType.id, ActionType.key).where(ActionType.user_id == user_id)
            )
        ).all()
    )
    feels = await db.execute(
        select(
            Task.task_type,
            Subtask.action_type_id,
            Task.action_type_id,
            Subtask.actual_feel,
            Subtask.done_at,
        )
        .join(Task, Task.id == Subtask.task_id)
        .where(
            Subtask.user_id == user_id,
            Subtask.deleted_at.is_(None),
            Task.deleted_at.is_(None),
            Subtask.status == SubtaskStatus.done,
            Subtask.actual_feel.is_not(None),
            Subtask.done_at.is_not(None),
        )
        .order_by(Subtask.done_at)
    )
    rows = await _rows(db, user_id)
    history: dict[Key, list[Feel]] = defaultdict(list)
    for task_type, sub_type, task_type_id, feel, done_at in feels.all():
        key = (task_type, keys.get(sub_type or task_type_id, DEFAULT_ACTION))
        row = rows.get(key)
        if row is not None and row.reset_at is not None and done_at <= row.reset_at:
            continue
        history[key].append(Feel(feel))

    for key in rows.keys() | history.keys():
        feels_of = history.get(key, [])
        row = rows.get(key)
        if row is None:
            row = Calibration(user_id=user_id, task_type=key[0], action_type=key[1])
            db.add(row)
        row.coef = coefficient(feels_of)
        row.samples = len(feels_of)


async def coefficients(db: AsyncSession, user_id: uuid.UUID) -> dict[Key, float]:
    return {k: r.coef for k, r in (await _rows(db, user_id)).items() if r.samples}


async def list_calibrations(db: AsyncSession, user_id: uuid.UUID) -> list[Calibration]:
    rows = await _rows(db, user_id)
    return sorted(
        (r for r in rows.values() if r.samples), key=lambda r: (r.task_type, r.action_type)
    )


async def reset(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Все коэффициенты → 1; старые отметки больше не учитываются."""
    now = now_utc()
    for row in (await _rows(db, user_id)).values():
        row.reset_at = now
        row.coef = 1.0
        row.samples = 0
    await db.commit()

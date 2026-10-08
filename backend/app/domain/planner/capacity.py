"""Сколько свободного времени до дедлайна (для разбивки ИИ, M10.2).

Оценка без солвера: свободные слоты (вне жёсткого, в окнах типа действия, до
дедлайна) с учётом дневного лимита учёбы, минус то, что уже нужно другим
блокам с дедлайном не позже этого. Минимум отдыха не вычитается — оценка
слегка оптимистичная, этого достаточно для «хватает / впритык / не хватает».
"""

from collections import defaultdict
from dataclasses import replace
from datetime import datetime

from app.domain.planner.contracts import Block, BlockId, PlanInput, Window
from app.domain.planner.grid import prepare

PROBE = "__capacity_probe__"


def free_minutes(
    inp: PlanInput,
    *,
    deadline: datetime,
    windows: tuple[Window, ...] = (),
    counts_as_study: bool = True,
    exclude_group: BlockId | None = None,
) -> int:
    """Свободные минуты от `inp.now` до `deadline` для блока с такими окнами.

    `exclude_group` — блоки этого задания не считаются конкурентами (их как раз
    и разбиваем заново).
    """
    others = tuple(b for b in inp.blocks if exclude_group is None or b.group_id != exclude_group)
    probe = Block(
        id=PROBE,
        duration_min=inp.grid_min,
        deadline=deadline,
        windows=windows,
        counts_as_study=counts_as_study,
    )
    prep = prepare(replace(inp, blocks=(*others, probe)))
    pb = prep.by_id[PROBE]
    if pb.overdue:
        return 0

    per_day: dict[int, int] = defaultdict(int)
    for lo, hi in pb.free:
        per_day[prep.day_of(lo)] += hi - lo
    capacity = 0
    for day, slots in per_day.items():
        if counts_as_study:
            slots = min(slots, max(0, prep.limit(day) - prep.fixed_study.get(day, 0)))
        capacity += slots

    demand = sum(
        other.dur
        for other in prep.blocks
        if other.id != PROBE
        and other.block.deadline is not None
        and other.block.deadline <= deadline
        and (other.block.counts_as_study or not counts_as_study)
    )
    return max(0, capacity - demand) * prep.grid.step_min

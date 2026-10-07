"""Проверка решения на жёсткие ограничения.

Страховка в `solve` (решение с нарушениями не отдаём) и основа property-тестов.
"""

from collections import defaultdict
from itertools import pairwise

from app.domain.planner.contracts import BlockId
from app.domain.planner.cpsat import Solution
from app.domain.planner.grid import Interval, Prepared, overlaps


def _inside(part: Interval, segments: list[Interval]) -> bool:
    return any(lo <= part[0] and part[1] <= hi for lo, hi in segments)


def violations(prep: Prepared, solution: Solution) -> list[str]:
    errors: list[str] = []
    padded: list[tuple[Interval, str]] = [
        ((lo, hi + prep.pad_for(hi - lo)), f"fixed {f.id}") for (lo, hi), f in prep.fixed if lo < hi
    ]
    plain: list[Interval] = []
    study: dict[int, int] = defaultdict(int)
    per_group: dict[tuple[BlockId, int], int] = defaultdict(int)

    for block_id, parts in solution.items():
        pb = prep.by_id.get(block_id)
        if pb is None:
            errors.append(f"{block_id}: неизвестный блок")
            continue
        if not parts or len(parts) > (2 if pb.split else 1):
            errors.append(f"{block_id}: {len(parts)} частей")
            continue
        if sum(hi - lo for lo, hi in parts) != pb.dur:
            errors.append(f"{block_id}: сумма частей ≠ оценке")
        if len(parts) == 2:
            if any(hi - lo < prep.min_part for lo, hi in parts):
                errors.append(f"{block_id}: часть короче минимума")
            if parts[1][0] < parts[0][1]:
                errors.append(f"{block_id}: части не по порядку")
        days = set()
        for lo, hi in parts:
            if not _inside((lo, hi), pb.free):
                errors.append(f"{block_id}: вне допустимого времени [{lo}, {hi})")
            padded.append(((lo, hi + prep.pad_for(hi - lo)), str(block_id)))
            plain.append((lo, hi))
            day = prep.day_of(lo)
            days.add(day)
            if pb.block.counts_as_study:
                study[day] += hi - lo
        if pb.block.group_id is not None:
            for day in days:
                per_group[(pb.block.group_id, day)] += 1
        for dep in pb.block.depends_on:
            if dep in prep.by_id:
                if dep not in solution:
                    errors.append(f"{block_id}: зависимость {dep} не размещена")
                elif solution[dep][-1][1] > parts[0][0]:
                    errors.append(f"{block_id}: начинается раньше конца {dep}")
            elif dep in prep.fixed_by_id and prep.fixed_by_id[dep][1] > parts[0][0]:
                errors.append(f"{block_id}: начинается раньше конца закреплённого {dep}")

    padded.sort()
    for (a, name_a), (b, name_b) in pairwise(padded):
        if overlaps(a, b):
            errors.append(f"пересечение {name_a} и {name_b}")

    for day, used in study.items():
        if used + prep.fixed_study.get(day, 0) > prep.study_limit and used:
            errors.append(f"день {day}: учёба {used} слотов сверх лимита")
    for (group, day), count in per_group.items():
        if count + prep.fixed_per_group.get((group, day), 0) > prep.max_per_group:
            errors.append(f"день {day}: задание {group} — {count} подзадач")

    for windows, required in (
        (prep.evenings, prep.evenings_required),
        (prep.halves, prep.halves_required),
    ):
        free: dict[tuple[int, int], int] = defaultdict(int)
        for w in windows:
            if not any(overlaps((w.lo, w.hi), p) for p in plain):
                free[w.week] += 1
        for week, need in required.items():
            if free[week] < need:
                errors.append(f"неделя {week}: отдыха {free[week]} из {need}")
    return errors

"""Жадный планировщик: fallback, если CP-SAT не успел, и стартовая подсказка для него.

Порядок — EDF: просроченные, затем ближе внутренний срок, затем узкие окна
(«связь с людьми» раньше учёбы), затем приоритет. Блок ставится в самое раннее
допустимое место: сначала целиком до внутреннего срока, потом разрезанным,
потом то же самое до настоящего дедлайна. Отдых резервируется заранее — самые
поздние вечера и половины выходных недели (EDF заполняет начало недели).
"""

from collections import defaultdict

from app.domain.planner.contracts import BlockId
from app.domain.planner.cpsat import Solution, effective_priority
from app.domain.planner.grid import Interval, Prepared, PreparedBlock, RestWindow

# Сколько стартов первой части пробовать при разрезании
SPLIT_TRIES = 40


class _State:
    def __init__(self, prep: Prepared) -> None:
        self.prep = prep
        n = prep.grid.n
        size = n + 64
        self.padded = bytearray(size)  # гибкие и закреплённые блоки с перерывом после
        self.rest = bytearray(size)  # выбранные окна отдыха
        self.study: dict[int, int] = dict(prep.fixed_study)
        self.per_group: dict[tuple[BlockId, int], int] = dict(prep.fixed_per_group)
        for (lo, hi), _ in prep.fixed:
            if lo < hi:
                self.padded[lo : hi + prep.pad_for(hi - lo)] = b"\x01" * (
                    hi - lo + prep.pad_for(hi - lo)
                )
        self._reserve_rest(prep.evenings, prep.evenings_required)
        self._reserve_rest(prep.halves, prep.halves_required)

    def _reserve_rest(self, windows: list[RestWindow], required: dict) -> None:
        by_week: dict[tuple[int, int], list[RestWindow]] = defaultdict(list)
        for w in windows:
            by_week[w.week].append(w)
        for week, ws in by_week.items():
            for w in sorted(ws, key=lambda w: -w.lo)[: required.get(week, 0)]:
                self.rest[w.lo : w.hi] = b"\x01" * (w.hi - w.lo)

    def blocker(self, pb: PreparedBlock, s: int, length: int, days_used: set[int]) -> int | None:
        """None — часть [s, s+length) можно ставить; иначе — следующий старт для проверки."""
        prep = self.prep
        pad = prep.pad_for(length)
        hit = self.padded.find(1, s, s + length + pad)
        if hit == -1:
            hit = self.rest.find(1, s, s + length)
        if hit != -1:
            return hit + 1
        day = prep.day_of(s)
        next_day = prep.days[day + 1].lo if day + 1 < len(prep.days) else prep.grid.n
        if pb.block.counts_as_study and self.study.get(day, 0) + length > prep.study_limit:
            return next_day
        group = pb.block.group_id
        if (
            group is not None
            and day not in days_used
            and self.per_group.get((group, day), 0) >= prep.max_per_group
        ):
            return next_day
        return None

    def find(
        self,
        pb: PreparedBlock,
        length: int,
        lower: int,
        end_limit: int,
        days_used: set[int] = frozenset(),  # type: ignore[assignment]
    ) -> int | None:
        for lo, hi in pb.free:
            hi = min(hi, end_limit)
            s = max(lo, lower)
            while s + length <= hi:
                nxt = self.blocker(pb, s, length, days_used)
                if nxt is None:
                    return s
                s = max(nxt, s + 1)
        return None

    def find_split(self, pb: PreparedBlock, lower: int, end_limit: int) -> list[Interval] | None:
        mp = self.prep.min_part
        tries = 0
        for lo, hi in pb.free:
            hi = min(hi, end_limit)
            s = max(lo, lower)
            while s + mp <= hi and tries < SPLIT_TRIES:
                if (nxt := self.blocker(pb, s, mp, set())) is not None:
                    s = max(nxt, s + 1)
                    continue
                tries += 1
                for len1 in range(min(pb.dur - mp, hi - s), mp - 1, -1):
                    if self.blocker(pb, s, len1, set()) is not None:
                        continue
                    day = self.prep.day_of(s)
                    # первая часть ещё не учтена в лимитах — проверяем вторую с запасом
                    self.commit(pb, [(s, s + len1)])
                    s2 = self.find(pb, pb.dur - len1, s + len1, end_limit, {day})
                    self.uncommit(pb, [(s, s + len1)])
                    if s2 is not None:
                        return [(s, s + len1), (s2, s2 + pb.dur - len1)]
                    break
                s += 1
        return None

    def _apply(self, pb: PreparedBlock, parts: list[Interval], sign: int) -> None:
        prep = self.prep
        days = set()
        for lo, hi in parts:
            end = hi + prep.pad_for(hi - lo)
            self.padded[lo:end] = (b"\x01" if sign > 0 else b"\x00") * (end - lo)
            day = prep.day_of(lo)
            days.add(day)
            if pb.block.counts_as_study:
                self.study[day] = self.study.get(day, 0) + sign * (hi - lo)
        if pb.block.group_id is not None:
            for day in days:
                key = (pb.block.group_id, day)
                self.per_group[key] = self.per_group.get(key, 0) + sign

    def commit(self, pb: PreparedBlock, parts: list[Interval]) -> None:
        self._apply(pb, parts, +1)

    def uncommit(self, pb: PreparedBlock, parts: list[Interval]) -> None:
        self._apply(pb, parts, -1)

    def place(self, pb: PreparedBlock, lower: int) -> list[Interval] | None:
        limits = [pb.latest_end]
        if pb.due is not None and pb.due < pb.latest_end:
            limits.insert(0, pb.due)
        for limit in limits:
            s = self.find(pb, pb.dur, lower, limit)
            if s is not None:
                return [(s, s + pb.dur)]
            if pb.split and (parts := self.find_split(pb, lower, limit)):
                return parts
        return None


def _order_key(pb: PreparedBlock) -> tuple:
    due = pb.due if pb.due is not None else pb.latest_end
    narrow = sum(hi - lo for lo, hi in pb.free)
    return (not pb.overdue, due, narrow, -effective_priority(pb), pb.index)


def solve_greedy(prep: Prepared) -> Solution:
    state = _State(prep)
    solution: Solution = {}
    failed: set[BlockId] = set()
    pending = {pb.id: pb for pb in prep.blocks}

    def deps(pb: PreparedBlock) -> list[BlockId]:
        return [d for d in pb.block.depends_on if d in prep.by_id and d != pb.id]

    keys = {pb.id: _order_key(pb) for pb in prep.blocks}
    while pending:
        ready = [pb for pb in pending.values() if not any(d in pending for d in deps(pb))]
        if not ready:  # цикл зависимостей — не ставим
            failed.update(pending)
            break
        pb = min(ready, key=lambda pb: keys[pb.id])
        del pending[pb.id]
        if any(d in failed for d in deps(pb)):
            failed.add(pb.id)
            continue
        lower = 0
        for d in pb.block.depends_on:
            if d in solution:
                lower = max(lower, solution[d][-1][1])
            elif d in prep.fixed_by_id:
                lower = max(lower, prep.fixed_by_id[d][1])
        parts = state.place(pb, lower)
        if parts is None:
            failed.add(pb.id)
            continue
        state.commit(pb, parts)
        solution[pb.id] = parts
    return solution

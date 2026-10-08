"""CP-SAT модель планировщика.

Каждый блок — одна или две (разрезанный) optional-части; presence = «размещён».
Свободное время зашито в домены стартов (сон, обед, пары, дорога, окна уже
вычтены в grid.py), поэтому NoOverlap нужен только между гибкими блоками,
закреплёнными блоками и выбранными окнами отдыха.

Жёстко: окна, дедлайн, зависимости, перерыв после длинных блоков, лимит учёбы
в день, ≤ N подзадач одного задания в день, минимум отдыха.
Мягко (минимизируем): приоритет × время завершения, огромный штраф за
непостановку (у дел из ящика — на порядки меньше: только в оставшееся время),
опоздание к внутреннему сроку, сдвиг относительно прошлого плана
(сегодня/завтра — дорого), утро для «связи с людьми», разрезание, порядок шагов
задания (`sequence`).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import pairwise
from time import perf_counter

from ortools.sat.python import cp_model

from app.domain.planner.contracts import BlockId
from app.domain.planner.grid import Interval, Prepared, PreparedBlock

# Веса целевой функции (на слот сетки, где это время)
W_END = 4  # × приоритет: раньше закончить
W_MISS = 10_000_000  # × приоритет: блок не поставлен
W_MISS_FILLER = 20_000  # × приоритет: дело из ящика не поставлено
W_LATE = 400  # × приоритет: позже внутреннего срока
W_STABLE_NEAR = 40  # сдвиг блока, который стоял на сегодня/завтра
W_STABLE_FAR = 1  # сдвиг остальных
W_MORNING = 1  # «связь с людьми»: позже от начала дня
W_SPLIT = 200  # блок разрезан: только если иначе заметно хуже
W_ORDER = 300  # шаг задания начат раньше конца предыдущего по порядку
OVERDUE_BOOST = 3  # приоритет просроченного

# Больше переменных — presolve не успевает за 2 с, решаем без него
PRESOLVE_MAX_VARS = 8000

# Решение: block_id → [(lo, hi), …] по порядку частей
Solution = dict[BlockId, list[Interval]]

LinearExpr = cp_model.LinearExprT


@dataclass
class _Part:
    start: cp_model.IntVar
    end: cp_model.IntVar
    length: cp_model.IntVar | int
    pres: cp_model.IntVar
    days: dict[int, LinearExpr] = field(default_factory=dict)  # день → 0/1
    study: dict[int, LinearExpr] = field(default_factory=dict)  # день → слотов учёбы


@dataclass
class _Block:
    pb: PreparedBlock
    pres: cp_model.IntVar
    parts: list[_Part]


def effective_priority(pb: PreparedBlock) -> int:
    return max(1, pb.block.priority) * (OVERDUE_BOOST if pb.overdue else 1)


def miss_weight(pb: PreparedBlock) -> int:
    """Штраф за непостановку: дела из ящика — только в оставшееся время."""
    return effective_priority(pb) * (W_MISS_FILLER if pb.block.filler else W_MISS)


class _Builder:
    def __init__(self, prep: Prepared) -> None:
        self.prep = prep
        self.m = cp_model.CpModel()
        self.blocks: dict[BlockId, _Block] = {}
        self.padded: list[cp_model.IntervalVar] = []
        self.plain: list[cp_model.IntervalVar] = []
        self.objective: list[LinearExpr] = []

    # ---------- части ----------

    def _days_of_domain(self, pb: PreparedBlock) -> list[tuple[int, int, int]]:
        """(день, первый старт, последний старт) — дни, где у блока есть старты."""
        spans: dict[int, list[int]] = {}
        for lo, hi in pb.starts.intervals:
            day = self.prep.day_of(lo)
            while lo <= hi:
                day_hi = self.prep.days[day + 1].lo - 1 if day + 1 < len(self.prep.days) else hi
                end = min(hi, day_hi)
                if day in spans:
                    spans[day][1] = end
                else:
                    spans[day] = [lo, end]
                lo, day = end + 1, day + 1
        return [(day, lo, hi) for day, (lo, hi) in spans.items()]

    def _whole(self, pb: PreparedBlock, pres: cp_model.IntVar) -> _Part:
        m, n = self.m, self.prep.grid.n
        start = m.new_int_var_from_domain(
            cp_model.Domain.from_flat_intervals(pb.starts.flat()), f"s{pb.index}"
        )
        end = m.new_int_var(0, n, f"e{pb.index}")
        self.plain.append(m.new_optional_interval_var(start, pb.dur, end, pres, f"i{pb.index}"))
        self.padded.append(
            m.new_optional_fixed_size_interval_var(start, pb.dur + pb.pad, pres, f"p{pb.index}")
        )
        part = _Part(start, end, pb.dur, pres)
        xs = []
        for day, lo, hi in self._days_of_domain(pb):
            x = m.new_bool_var(f"x{pb.index}_{day}")
            m.add(start >= lo).only_enforce_if(x)
            m.add(start <= hi).only_enforce_if(x)
            xs.append(x)
            part.days[day] = x
            if pb.block.counts_as_study:
                part.study[day] = pb.dur * x
        m.add(sum(xs) == pres)
        return part

    def _segment_part(
        self,
        pb: PreparedBlock,
        k: int,
        pres: cp_model.IntVar,
        length: cp_model.IntVar,
        segments: list[Interval],
    ) -> _Part:
        m, prep = self.m, self.prep
        n, name = prep.grid.n, f"{pb.index}_{k}"
        start = m.new_int_var(0, n, f"s{name}")
        end = m.new_int_var(0, n, f"e{name}")
        self.plain.append(m.new_optional_interval_var(start, length, end, pres, f"i{name}"))
        pad = prep.pad_for(pb.dur)
        if pad:
            long = m.new_bool_var(f"long{name}")
            threshold = prep.grid.slots(prep.inp.settings.long_block_min)
            m.add(length > threshold).only_enforce_if(long)
            m.add(length <= threshold).only_enforce_if(long.Not())
            size = m.new_int_var(0, pb.dur + pad, f"ps{name}")
            m.add(size == length + pad * long)
            pend = m.new_int_var(0, n + pad, f"pe{name}")
            self.padded.append(m.new_optional_interval_var(start, size, pend, pres, f"p{name}"))
        else:
            self.padded.append(self.plain[-1])

        part = _Part(start, end, length, pres)
        by_day: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for j, (lo, hi) in enumerate(segments):
            s = m.new_bool_var(f"g{name}_{j}")
            m.add(start >= lo).only_enforce_if(s)
            m.add(end <= hi).only_enforce_if(s)
            by_day[prep.day_of(lo)].append(s)
        m.add(sum(v for vs in by_day.values() for v in vs) == pres)
        for day, vs in by_day.items():
            x = sum(vs)
            part.days[day] = x
            if pb.block.counts_as_study:
                minutes = m.new_int_var(0, pb.dur, f"m{name}_{day}")
                m.add(minutes <= pb.dur * x)
                m.add(minutes <= length)
                m.add(minutes >= length - pb.dur * (1 - x))
                part.study[day] = minutes
        return part

    def _split(self, pb: PreparedBlock, pres: cp_model.IntVar) -> list[_Part]:
        m, mp = self.m, self.prep.min_part
        segments = pb.part_free(mp)
        pres2 = m.new_bool_var(f"split{pb.index}")
        len1 = m.new_int_var(mp, pb.dur, f"l{pb.index}_0")
        len2 = m.new_int_var(mp, pb.dur - mp, f"l{pb.index}_1")
        m.add_implication(pres2, pres)
        m.add(len1 + len2 == pb.dur).only_enforce_if(pres2)
        m.add(len1 == pb.dur).only_enforce_if(pres2.Not())
        m.add(len2 == mp).only_enforce_if(pres2.Not())
        p1 = self._segment_part(pb, 0, pres, len1, segments)
        p2 = self._segment_part(pb, 1, pres2, len2, segments)
        m.add(p2.start >= p1.end).only_enforce_if(pres2)
        self.objective.append(W_SPLIT * pres2)
        return [p1, p2]

    def add_blocks(self) -> None:
        for pb in self.prep.blocks:
            if pb.split and pb.part_free(self.prep.min_part):
                pres = self.m.new_bool_var(f"on{pb.index}")
                parts = self._split(pb, pres)
            elif pb.starts:
                pres = self.m.new_bool_var(f"on{pb.index}")
                parts = [self._whole(pb, pres)]
            else:
                continue
            self.blocks[pb.id] = _Block(pb, pres, parts)

    # ---------- общие ограничения ----------

    def add_fixed(self) -> None:
        for (lo, hi), _ in self.prep.fixed:
            if lo >= hi:
                continue
            pad = self.prep.pad_for(hi - lo)
            self.padded.append(self.m.new_fixed_size_interval_var(lo, hi - lo + pad, f"f{lo}"))

    def add_rest(self) -> None:
        prep = self.prep
        for windows, required in (
            (prep.evenings, prep.evenings_required),
            (prep.halves, prep.halves_required),
        ):
            if not windows or not any(required.values()):
                continue
            by_week: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
            intervals = []
            for i, w in enumerate(windows):
                r = self.m.new_bool_var(f"rest{w.lo}_{i}")
                intervals.append(
                    self.m.new_optional_fixed_size_interval_var(w.lo, w.hi - w.lo, r, f"r{w.lo}")
                )
                by_week[w.week].append(r)
            for week, rs in by_week.items():
                self.m.add(sum(rs) >= required.get(week, 0))
            self.m.add_no_overlap(self.plain + intervals)

    def add_dependencies(self) -> None:
        m, prep = self.m, self.prep
        for b in self.blocks.values():
            first = b.parts[0]
            for dep in b.pb.block.depends_on:
                if dep in self.blocks:
                    a = self.blocks[dep]
                    m.add_implication(b.pres, a.pres)
                    for p in a.parts:
                        m.add(first.start >= p.end).only_enforce_if([b.pres, p.pres])
                elif dep in prep.by_id:
                    m.add(b.pres == 0)  # зависимость поставить негде
                elif dep in prep.fixed_by_id:
                    m.add(first.start >= prep.fixed_by_id[dep][1]).only_enforce_if(b.pres)

    def add_daily(self) -> None:
        prep, m = self.prep, self.m
        study: dict[int, list[LinearExpr]] = defaultdict(list)
        per_group: dict[tuple[BlockId, int], list[LinearExpr]] = defaultdict(list)
        for b in self.blocks.values():
            for p in b.parts:
                for day, expr in p.study.items():
                    study[day].append(expr)
            group = b.pb.block.group_id
            if group is None:
                continue
            days = {d for p in b.parts for d in p.days}
            for day in days:
                xs = [p.days[day] for p in b.parts if day in p.days]
                if len(xs) == 1:
                    per_group[(group, day)].append(xs[0])
                else:
                    y = m.new_bool_var(f"y{b.pb.index}_{day}")
                    for x in xs:
                        m.add(y >= x)
                    per_group[(group, day)].append(y)
        for day, exprs in study.items():
            m.add(sum(exprs) <= max(0, prep.limit(day) - prep.fixed_study.get(day, 0)))
        for key, exprs in per_group.items():
            if len(exprs) + prep.fixed_per_group.get(key, 0) > prep.max_per_group:
                m.add(sum(exprs) <= max(0, prep.max_per_group - prep.fixed_per_group.get(key, 0)))

    def add_order(self) -> None:
        """Мягкий порядок шагов: соседние по `sequence` в задании — штраф, если
        следующий начат раньше конца предыдущего (оба размещены)."""
        by_group: dict[BlockId, list[_Block]] = defaultdict(list)
        for b in self.blocks.values():
            if b.pb.block.group_id is not None and b.pb.block.sequence is not None:
                by_group[b.pb.block.group_id].append(b)
        for items in by_group.values():
            items.sort(key=lambda b: (b.pb.block.sequence, b.pb.index))
            for a, b in pairwise(items):
                if a.pb.id in b.pb.block.depends_on:
                    continue  # и так жёстко
                inv = self.m.new_bool_var(f"ord{a.pb.index}_{b.pb.index}")
                for p in a.parts:
                    self.m.add(b.parts[0].start >= p.end).only_enforce_if(
                        [b.pres, p.pres, inv.Not()]
                    )
                self.objective.append(W_ORDER * inv)

    def add_no_overlap(self) -> None:
        self.m.add_no_overlap(self.padded)

    # ---------- цель ----------

    def add_objective(self) -> None:
        m, prep, n = self.m, self.prep, self.prep.grid.n
        previous = defaultdict(dict)
        for pl in prep.inp.previous:
            slot = prep.grid.floor(pl.start)
            if 0 <= slot < n:
                previous[pl.block_id][pl.part] = slot
        for b in self.blocks.values():
            pb, prio = b.pb, effective_priority(b.pb)
            last = m.new_int_var(0, n, f"last{pb.index}")
            if len(b.parts) == 1:
                m.add(last == b.parts[0].end).only_enforce_if(b.pres)
            else:
                p1, p2 = b.parts
                m.add(last == p1.end).only_enforce_if([b.pres, p2.pres.Not()])
                m.add(last == p2.end).only_enforce_if(p2.pres)
            m.add(last == 0).only_enforce_if(b.pres.Not())
            self.objective.append(prio * W_END * last)
            self.objective.append(miss_weight(pb) * (1 - b.pres))
            if pb.due is not None:
                late = m.new_int_var(0, n, f"late{pb.index}")
                m.add(late >= last - pb.due)
                self.objective.append(prio * W_LATE * late)
            for k, p in enumerate(b.parts):
                prev = previous.get(pb.id, {}).get(k)
                if prev is None:
                    continue
                dev = m.new_int_var(0, n, f"dev{pb.index}_{k}")
                m.add(dev >= p.start - prev).only_enforce_if(p.pres)
                m.add(dev >= prev - p.start).only_enforce_if(p.pres)
                near = prep.day_of(prev) in (0, 1)
                self.objective.append((W_STABLE_NEAR if near else W_STABLE_FAR) * dev)
            if pb.block.prefer_morning:
                first = b.parts[0]
                day_lo = {d.index: d.lo for d in prep.days}
                tod = m.new_int_var(0, n, f"tod{pb.index}")
                since = first.start - sum(day_lo[d] * x for d, x in first.days.items())
                m.add(tod == since).only_enforce_if(b.pres)
                self.objective.append(W_MORNING * tod)
        m.minimize(sum(self.objective))

    # ---------- подсказка ----------

    def add_hint(self, hint: Solution) -> None:
        for block_id, b in self.blocks.items():
            parts = hint.get(block_id)
            self.m.add_hint(b.pres, bool(parts))
            if not parts:
                continue
            if len(b.parts) == 2:
                self.m.add_hint(b.parts[1].pres, len(parts) == 2)
            for p, (lo, hi) in zip(b.parts, parts, strict=False):
                self.m.add_hint(p.start, lo)
                self.m.add_hint(p.end, hi)
                if isinstance(p.length, cp_model.IntVar):
                    self.m.add_hint(p.length, hi - lo)

    def extract(self, solver: cp_model.CpSolver) -> Solution:
        solution: Solution = {}
        for block_id, b in self.blocks.items():
            if not solver.boolean_value(b.pres):
                continue
            solution[block_id] = [
                (solver.value(p.start), solver.value(p.end))
                for p in b.parts
                if solver.boolean_value(p.pres)
            ]
        return solution


def _params(solver: cp_model.CpSolver, time_limit_s: float, workers: int, presolve: bool) -> None:
    solver.parameters.max_time_in_seconds = max(time_limit_s, 0.01)
    solver.parameters.num_workers = workers
    # Probing (а на больших моделях и весь presolve) съедает бюджет, не найдя ни одного решения
    solver.parameters.cp_model_probing_level = 0
    solver.parameters.cp_model_presolve = presolve


def _complete_hint(builder: _Builder, hint: Solution, time_limit_s: float, workers: int) -> bool:
    """Достраивает подсказку до значений всех переменных.

    Неполную подсказку (только старты) CP-SAT на большой модели достроить не
    успевает. Поэтому фиксируем размещения в копии модели, решаем её (быстро)
    и подсказываем исходной модели полное допустимое решение.
    """
    fixed = builder.m.clone()
    for block_id, b in builder.blocks.items():
        parts = hint.get(block_id, [])
        fixed.add(b.pres == bool(parts))
        if len(b.parts) == 2:
            fixed.add(b.parts[1].pres == (len(parts) == 2))
        for p, (lo, hi) in zip(b.parts, parts, strict=False):
            fixed.add(p.start == lo)
            fixed.add(p.end == hi)
    solver = cp_model.CpSolver()
    # Все старты зафиксированы — распространения достаточно, presolve только мешает
    _params(solver, time_limit_s, workers, presolve=False)
    if solver.solve(fixed) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return False
    builder.m.clear_hints()
    hint_proto = builder.m.proto.solution_hint
    values = solver.response_proto.solution
    hint_proto.vars.extend(range(len(values)))
    hint_proto.values.extend(values)
    return True


def solve_cp(
    prep: Prepared, hint: Solution | None, deadline: float, workers: int = 8
) -> tuple[str, Solution | None]:
    """Решает модель до момента `deadline` (perf_counter).

    Возвращает (статус, решение или None, если решения нет).
    """
    builder = _Builder(prep)
    builder.add_blocks()
    builder.add_fixed()
    builder.add_no_overlap()
    builder.add_rest()
    builder.add_dependencies()
    builder.add_daily()
    builder.add_order()
    builder.add_objective()
    if hint is not None:
        remaining = deadline - perf_counter()
        if not _complete_hint(builder, hint, remaining * 0.4, workers):
            builder.add_hint(hint)

    solver = cp_model.CpSolver()
    presolve = len(builder.m.proto.variables) <= PRESOLVE_MAX_VARS
    _params(solver, deadline - perf_counter(), workers, presolve)
    status = solver.solve(builder.m)
    name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return name, None
    return name, builder.extract(solver)

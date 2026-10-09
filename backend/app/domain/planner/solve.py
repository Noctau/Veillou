"""`solve(PlanInput) -> PlanResult` — точка входа планировщика.

1. grid.prepare: сетка, доступность каждого блока, кандидаты отдыха.
2. Жадное решение (быстро, всегда есть) — подсказка для CP-SAT.
3. CP-SAT с остатком бюджета времени. Берём его решение, если оно есть,
   проходит проверку и ставит не меньше блоков (с учётом приоритета), чем жадное.
4. at_risk, diff с прошлым планом, статистика. Если что-то не влезло, жадное
   решение без минимума отдыха показывает, не отдых ли тому причина (`rest`).
   Недобор нормы проекта (от получаса) — угроза `quota` на саму норму;
   неразмещённый резерв нормы угрозой не считается.
"""

from collections.abc import Iterable
from dataclasses import replace
from datetime import timedelta
from time import perf_counter

from app.domain.planner.check import violations
from app.domain.planner.contracts import (
    AtRisk,
    BlockId,
    Placement,
    PlanDiff,
    PlanInput,
    PlanResult,
    PlanStats,
    RiskReason,
)
from app.domain.planner.cpsat import Solution, miss_weight, solve_cp
from app.domain.planner.greedy import quota_shortfalls, solve_greedy
from app.domain.planner.grid import Prepared, prepare

# Запас на извлечение решения и сборку результата
RESERVE_S = 0.15


def _weight(prep: Prepared, solution: Solution) -> int:
    return sum(miss_weight(prep.by_id[b]) for b in solution)


def _placements(prep: Prepared, solution: Solution) -> list[Placement]:
    result = []
    for pb in prep.blocks:
        parts = solution.get(pb.id)
        if not parts:
            continue
        for k, (lo, hi) in enumerate(parts):
            start = prep.grid.dt(lo)
            # Целый блок — точной длины; части разрезанного — по сетке
            end = (
                start + timedelta(minutes=pb.block.duration_min)
                if len(parts) == 1
                else prep.grid.dt(hi)
            )
            result.append(Placement(pb.id, k, start, end))
    return result


def _at_risk(prep: Prepared, solution: Solution) -> list[AtRisk]:
    result = []
    for pb in prep.blocks:
        if pb.block.reserve:
            continue
        reason: RiskReason | None = None
        parts = solution.get(pb.id)
        if parts is None:
            if any(d in prep.by_id and d not in solution for d in pb.block.depends_on):
                reason = RiskReason.dependency
            elif not pb.starts and not (pb.split and pb.part_free(prep.min_part)):
                reason = RiskReason.no_slots
            else:
                reason = RiskReason.no_time
        elif pb.overdue:
            reason = RiskReason.overdue
        elif pb.due is not None and parts[-1][1] > pb.due:
            reason = RiskReason.late
        if reason:
            result.append(AtRisk(pb.id, pb.block.group_id, reason))
    tags = {q.id: q.tag for q in prep.quotas}
    for quota_id, short in quota_shortfalls(prep, solution).items():
        if short >= prep.min_part:
            result.append(AtRisk(quota_id, tags[quota_id], RiskReason.quota))
    return result


def _blamed_on_rest(inp: PlanInput, risks: list[AtRisk]) -> list[AtRisk]:
    """no_time / late → rest, если без минимума отдыха блок встал бы (вовремя)."""
    s = inp.settings
    suspects = {r.block_id for r in risks if r.reason in (RiskReason.no_time, RiskReason.late)}
    if not suspects or not (s.free_evenings_per_week or s.weekend_half_days):
        return risks
    relaxed = prepare(
        replace(inp, settings=replace(s, free_evenings_per_week=0, weekend_half_days=0))
    )
    solution = solve_greedy(relaxed)
    fixed: set[BlockId] = set()
    for block_id in suspects:
        parts = solution.get(block_id)
        pb = relaxed.by_id[block_id]
        if parts and (pb.due is None or parts[-1][1] <= pb.due):
            fixed.add(block_id)
    return [replace(r, reason=RiskReason.rest) if r.block_id in fixed else r for r in risks]


def diff(previous: Iterable[Placement], current: Iterable[Placement]) -> PlanDiff:
    before = {(p.block_id, p.part): p for p in previous}
    after = {(p.block_id, p.part): p for p in current}
    return PlanDiff(
        added=tuple(p for k, p in after.items() if k not in before),
        removed=tuple(p for k, p in before.items() if k not in after),
        moved=tuple(
            (before[k], p)
            for k, p in after.items()
            if k in before and (before[k].start, before[k].end) != (p.start, p.end)
        ),
    )


def solve(inp: PlanInput) -> PlanResult:
    started = perf_counter()
    prep = prepare(inp)
    solution = solve_greedy(prep)
    engine, status = "greedy", "greedy"

    deadline = started + inp.time_limit_s - RESERVE_S
    if prep.blocks and deadline - perf_counter() > 0.05:
        status, cp = solve_cp(prep, solution, deadline)
        if (
            cp is not None
            and _weight(prep, cp) >= _weight(prep, solution)
            and not violations(prep, cp)
        ):
            solution, engine = cp, "cp_sat"

    placements = _placements(prep, solution)
    ids = {b.id for b in inp.blocks}
    return PlanResult(
        placements=tuple(placements),
        at_risk=tuple(_blamed_on_rest(inp, _at_risk(prep, solution))),
        diff=diff((p for p in inp.previous if p.block_id in ids), placements),
        stats=PlanStats(
            engine=engine,
            status=status,
            blocks=len(prep.blocks),
            placed=len(solution),
            split=sum(1 for parts in solution.values() if len(parts) > 1),
            elapsed_ms=round((perf_counter() - started) * 1000),
            horizon_start=prep.grid.t0,
            horizon_end=prep.grid.end,
        ),
    )

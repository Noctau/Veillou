"""Планировщик: чистая функция `solve(PlanInput) -> PlanResult`, без БД.

CP-SAT на сетке 15 минут с жадным fallback. Подробности — в модулях:
grid (доступность), cpsat (модель), greedy (fallback), check (инварианты).
"""

from app.domain.planner.capacity import free_minutes
from app.domain.planner.contracts import (
    AtRisk,
    Block,
    BlockId,
    Busy,
    FixedBlock,
    Placement,
    PlanDiff,
    PlanInput,
    PlanResult,
    PlanSettings,
    PlanStats,
    Quota,
    RiskReason,
    TimeRange,
    Window,
)
from app.domain.planner.grid import Domain, available_slots
from app.domain.planner.solve import solve

__all__ = [
    "AtRisk",
    "Block",
    "BlockId",
    "Busy",
    "Domain",
    "FixedBlock",
    "Placement",
    "PlanDiff",
    "PlanInput",
    "PlanResult",
    "PlanSettings",
    "PlanStats",
    "Quota",
    "RiskReason",
    "TimeRange",
    "Window",
    "available_slots",
    "free_minutes",
    "solve",
]

"""Калибровка оценок по отметкам «быстрее / как планировала / дольше».

Коэффициент — EMA по отношению «факт / план». План уже умножен на текущий
коэффициент, поэтому отметка «как планировала» его не меняет, а шаг —
мультипликативный: k ← k · (1 + α · (m − 1)), где m — множитель отметки.
Итог зависит только от набора отметок (не от порядка, пока не упёрлись в
границы), поэтому пересчитывается с нуля по истории — правка отметки задним
числом просто меняет историю.
"""

from collections.abc import Iterable

from app.domain.enums import Feel

ALPHA = 0.3
FEEL_FACTOR: dict[Feel, float] = {Feel.faster: 0.8, Feel.ok: 1.0, Feel.slower: 1.25}
MIN_COEF, MAX_COEF = 0.5, 2.0


def coefficient(feels: Iterable[Feel]) -> float:
    """Коэффициент по отметкам в хронологическом порядке. Без отметок — 1."""
    coef = 1.0
    for feel in feels:
        step = 1 + ALPHA * (FEEL_FACTOR[feel] - 1)
        coef = min(MAX_COEF, max(MIN_COEF, coef * step))
    return coef


def calibrated(estimate_min: int, coef: float) -> int:
    """Оценка с поправкой, не меньше 5 минут."""
    return max(5, round(estimate_min * coef))

"""M9.4: калибровка оценок."""

import pytest

from app.domain.calibration import MAX_COEF, MIN_COEF, calibrated, coefficient
from app.domain.enums import Feel


def test_no_feels_is_neutral():
    assert coefficient([]) == 1.0


def test_ok_does_not_change():
    assert coefficient([Feel.ok] * 10) == 1.0


def test_slower_grows_faster_shrinks():
    assert coefficient([Feel.slower]) == pytest.approx(1.075)
    assert coefficient([Feel.faster]) == pytest.approx(0.94)


def test_order_does_not_matter_inside_bounds():
    a = coefficient([Feel.slower, Feel.faster, Feel.slower])
    b = coefficient([Feel.faster, Feel.slower, Feel.slower])
    assert a == pytest.approx(b)


def test_clamped():
    assert coefficient([Feel.slower] * 100) == MAX_COEF
    assert coefficient([Feel.faster] * 100) == MIN_COEF


def test_comes_back_from_bound_quickly():
    # Упёрлись в верхнюю границу — одна «быстрее» сразу уводит вниз
    assert coefficient([Feel.slower] * 100 + [Feel.faster]) < MAX_COEF


def test_calibrated_estimate():
    assert calibrated(60, 1.25) == 75
    assert calibrated(5, 0.5) == 5
    assert calibrated(45, 1.0) == 45

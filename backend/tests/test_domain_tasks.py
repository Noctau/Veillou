import pytest

from app.domain.tasks import find_cycle, progress


@pytest.mark.parametrize(
    ("done", "total", "task_done", "expected"),
    [
        (0, 0, False, 0.0),
        (0, 0, True, 1.0),
        (1, 4, False, 0.25),
        (4, 4, False, 1.0),
        (5, 4, False, 1.0),  # защита от рассинхронизации
    ],
)
def test_progress(done, total, task_done, expected):
    assert progress(done, total, task_done=task_done) == expected


def test_no_cycle():
    assert find_cycle({"a": [], "b": ["a"], "c": ["a", "b"]}) is None
    assert find_cycle({}) is None


def test_self_loop():
    assert find_cycle({"a": ["a"]}) == ["a", "a"]


def test_cycle_found():
    cycle = find_cycle({"a": ["c"], "b": ["a"], "c": ["b"], "d": []})
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"a", "b", "c"}


def test_unknown_refs_ignored():
    assert find_cycle({"a": ["zzz"]}) is None

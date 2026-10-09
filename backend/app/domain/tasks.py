"""Чистая логика заданий: прогресс и зависимости подзадач."""

from collections.abc import Hashable, Mapping, Sequence

# Цвета узлов при обходе в глубину
_WHITE, _GREY, _BLACK = 0, 1, 2


def progress(done: int, total: int, *, task_done: bool = False) -> float:
    """Доля сделанных подзадач. Без подзадач — 1, если задание закрыто, иначе 0."""
    if total <= 0:
        return 1.0 if task_done else 0.0
    return min(done, total) / total


def find_cycle[K: Hashable](depends_on: Mapping[K, Sequence[K]]) -> list[K] | None:
    """Цикл в графе «подзадача → от чего зависит», если он есть (иначе None).

    Ссылки на неизвестные узлы игнорируются. Возвращает узлы цикла по порядку,
    первый узел повторяется в конце: [a, b, a].
    """
    color: dict[K, int] = dict.fromkeys(depends_on, _WHITE)
    stack: list[K] = []

    def visit(node: K) -> list[K] | None:
        color[node] = _GREY
        stack.append(node)
        for dep in depends_on.get(node, ()):
            if dep not in color:
                continue
            if color[dep] == _GREY:
                return [*stack[stack.index(dep) :], dep]
            if color[dep] == _WHITE and (cycle := visit(dep)):
                return cycle
        stack.pop()
        color[node] = _BLACK
        return None

    for node in depends_on:
        if color[node] == _WHITE and (cycle := visit(node)):
            return cycle
    return None

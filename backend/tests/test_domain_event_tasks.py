"""M19.1: окно и название автозадачи (domain/event_tasks.py)."""

from datetime import UTC, datetime, timedelta

from app.domain.enums import EventRuleWhen
from app.domain.event_tasks import LOOKAHEAD, RuleWindow, Window, render_title, window

START = datetime(2026, 10, 14, 13, tzinfo=UTC)
END = START + timedelta(hours=1)
BEFORE = RuleWindow(EventRuleWhen.before, offset_min=30)


def test_before_finish_offset_and_after_previous():
    prev_end = START - timedelta(days=3)
    assert window(BEFORE, START, END, prev_end=prev_end) == Window(
        prev_end, START - timedelta(minutes=30)
    )


def test_before_without_previous_looks_ahead_week():
    assert window(BEFORE, START, END) == Window(START - LOOKAHEAD, START - timedelta(minutes=30))
    far = START - timedelta(days=30)
    assert window(BEFORE, START, END, prev_end=far).earliest == START - LOOKAHEAD


def test_after_within_days():
    rule = RuleWindow(EventRuleWhen.after, within_days=2)
    assert window(rule, START, END) == Window(END, END + timedelta(days=2))


def test_after_until_next_and_within_earliest_wins():
    rule = RuleWindow(EventRuleWhen.after, within_days=5, until_next=True)
    nxt = START + timedelta(days=3)
    assert window(rule, START, END, next_start=nxt) == Window(END, nxt)
    # следующего вхождения нет — остаётся «через N дней»
    assert window(rule, START, END).deadline == END + timedelta(days=5)


def test_after_without_deadline():
    assert window(RuleWindow(EventRuleWhen.after), START, END) == Window(END, None)


def test_render_title_placeholders():
    title = render_title(
        "Подготовить урок — {area} ({field:Тема})",
        event="Урок",
        area="Маша",
        fields={"f1": "дроби", "Тема": "дроби"},
    )
    assert title == "Подготовить урок — Маша (дроби)"
    assert render_title("{event}: {FIELD: f1}", event="Урок", area=None, fields={"f1": "x"}) == (
        "Урок: x"
    )


def test_render_title_missing_values_trimmed():
    assert render_title("Проверить ДЗ — {area}", event="Урок", area=None) == "Проверить ДЗ"
    assert render_title("{area}", event="Урок", area=None) == "Урок"
    assert render_title("{field:нет}  итог", event="Урок", area=None) == "итог"


def test_render_title_russian_tokens():
    title = render_title(
        "Проверить ДЗ — {сфера}: {поле:тема} ({Событие})",
        event="Урок",
        area="Маша",
        fields={"Тема": "дроби"},
    )
    assert title == "Проверить ДЗ — Маша: дроби (Урок)"

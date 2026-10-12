"""Промпты на конфигурации пользователя (M21.2): кто пользователь — из «о себе»,
списки — из его справочников; описания конкретного человека в коде нет."""

from datetime import date, datetime

import pytest

from app.ai.prompts import (
    ROLE,
    AreaHint,
    BreakdownContext,
    Hint,
    MilestonesContext,
    ParseContext,
    Profile,
    breakdown_messages,
    milestones_messages,
    parse_messages,
    photo_messages,
    who,
)

TUTOR = Profile(
    about="Репетитор по математике, занимаюсь со школьниками онлайн.",
    areas=[AreaHint("Маша", "Ученик"), AreaHint("Петя Иванов", "Ученик", ("петя",))],
    task_types=[Hint("Проверка ДЗ", ("проверить дз",)), Hint("Подготовка урока")],
    action_types=[Hint("Связь с людьми", ("позвонить",)), Hint("Подготовка")],
    categories=["Работа", "Личное"],
)
NOW = datetime(2026, 10, 12, 10, 0)
# Лексика студентки Part 1 не должна жить в коде промптов
STUDENT_WORDS = ("студент", "научрук", "семестр", "пара", "вкр", "кафедр", "мгу", "предмет")


def all_prompts(profile: Profile) -> str:
    messages = [
        *breakdown_messages(BreakdownContext("Задание", date(2026, 10, 12), profile=profile)),
        *parse_messages(ParseContext("текст", NOW, profile)),
        *photo_messages(ParseContext("", NOW, profile)),
        *milestones_messages(MilestonesContext("Проект", date(2026, 10, 12), profile=profile)),
    ]
    return "\n".join(m.content for m in messages)


def test_who_without_about_is_just_role():
    assert who(Profile()) == ROLE
    assert who(Profile(about="  ")) == ROLE
    long = who(Profile(about="x " * 2000))
    assert len(long) < len(ROLE) + 1100


@pytest.mark.parametrize("word", STUDENT_WORDS)
def test_no_student_words_in_code(word):
    text = all_prompts(Profile()).lower()
    assert f" {word}" not in text, word
    assert f"«{word}" not in text, word


def test_profile_lists_reach_prompts():
    text = all_prompts(TUTOR)
    assert "О пользователе (с его слов): Репетитор по математике" in text
    assert "- Маша (Ученик)" in text
    assert "- Петя Иванов (Ученик, петя)" in text
    assert "- Проверка ДЗ (проверить дз)" in text
    assert "- Связь с людьми (позвонить)" in text
    assert "Категории (category — одно название из списка или пустая строка): Работа, Личное" in (
        text
    )


def test_empty_profile_says_lists_are_empty():
    text = all_prompts(Profile())
    assert "Сфер в списке нет" in text
    assert "Типов задач в списке нет" in text
    assert "Типов действий в списке нет" in text
    assert "Категорий в списке нет" in text


def test_breakdown_area_and_milestone_pauses():
    [_, user] = breakdown_messages(
        BreakdownContext("Подготовить урок", date(2026, 10, 12), area="Маша (Ученик)")
    )
    assert "Сфера: Маша (Ученик)" in user.content
    messages = milestones_messages(
        MilestonesContext(
            "Диплом",
            date(2026, 10, 12),
            pauses=["Сессия (Осень 2026): 2027-01-09 — 2027-01-25"],
        )
    )
    assert "- Сессия (Осень 2026): 2027-01-09 — 2027-01-25" in messages[-1].content

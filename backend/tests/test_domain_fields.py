import uuid

import pytest

from app.domain.enums import FieldType
from app.domain.fields import (
    FieldDef,
    FieldError,
    area_refs,
    dump_defs,
    merge_defs,
    parse_defs,
    render_values,
    validate_defs,
    validate_values,
)

TEACHERS = FieldDef("teachers", "Преподаватели", FieldType.contact, multiple=True)
CONTROL = FieldDef(
    "control_form",
    "Форма контроля",
    FieldType.select,
    options=("Экзамен", "Зачёт", "Дифзачёт"),
    show_in_reminder=True,
)
LINKS = FieldDef("links", "Ссылки", FieldType.link, multiple=True)
DEFS = [TEACHERS, CONTROL, LINKS]


def one(type: FieldType, value: object, **kw: object) -> object:
    d = FieldDef("x", "Поле", type, **kw)  # type: ignore[arg-type]
    return validate_values([d], {"x": value}).get("x")


# ---------- типы значений ----------


def test_text_stripped_and_empty_dropped():
    assert one(FieldType.text, "  9 «Б»  ") == "9 «Б»"
    assert one(FieldType.text, "   ") is None


def test_text_too_long():
    with pytest.raises(FieldError, match="длиннее"):
        one(FieldType.text, "а" * 2001)


def test_number_accepts_ints_floats_and_comma_strings():
    assert one(FieldType.number, 1500) == 1500
    assert one(FieldType.number, 1.5) == 1.5
    assert one(FieldType.number, "1,5") == 1.5
    assert one(FieldType.number, "2000.0") == 2000
    assert isinstance(one(FieldType.number, 3.0), int)


@pytest.mark.parametrize("bad", [True, "много", float("nan"), {"a": 1}])
def test_number_rejects_non_numbers(bad: object):
    with pytest.raises(FieldError, match="число"):
        one(FieldType.number, bad)


def test_bool_false_is_a_value():
    assert one(FieldType.bool, False) is False
    with pytest.raises(FieldError):
        one(FieldType.bool, "да")


def test_select_in_list_case_insensitive():
    assert validate_values([CONTROL], {"control_form": "зачёт"}) == {"control_form": "Зачёт"}


def test_select_outside_list():
    with pytest.raises(FieldError, match="«Курсовая» нет среди вариантов"):
        validate_values([CONTROL], {"control_form": "Курсовая"})


def test_multiselect_ordered_by_options_and_deduplicated():
    d = FieldDef("days", "Дни", FieldType.multiselect, options=("пн", "ср", "пт"))
    assert validate_values([d], {"days": ["пт", "пн", "пт"]}) == {"days": ["пн", "пт"]}
    assert validate_values([d], {"days": []}) == {}
    with pytest.raises(FieldError):
        validate_values([d], {"days": ["вс"]})


def test_date_iso():
    assert one(FieldType.date, "2026-10-12") == "2026-10-12"
    with pytest.raises(FieldError, match="дата"):
        one(FieldType.date, "12.10.2026")


def test_link_from_string_and_object():
    assert one(FieldType.link, "https://example.com/a") == {
        "title": "",
        "url": "https://example.com/a",
    }
    assert one(FieldType.link, {"title": " Курс ", "url": "https://x.ru"}) == {
        "title": "Курс",
        "url": "https://x.ru",
    }
    with pytest.raises(FieldError, match="http"):
        one(FieldType.link, "javascript:alert(1)")


def test_contact_cleaned_unknown_keys_dropped():
    value = {"name": " Иванов ", "role": "лектор", "email": "i@x.ru", "skype": "ivan", "phone": ""}
    assert one(FieldType.contact, value) == {"name": "Иванов", "role": "лектор", "email": "i@x.ru"}
    assert one(FieldType.contact, {"name": "", "role": ""}) is None
    with pytest.raises(FieldError, match="email"):
        one(FieldType.contact, {"email": "нет"})


def test_contact_list():
    values = {
        "teachers": [
            {"name": "Иванов Пётр Сергеевич", "role": "лектор", "email": "ivanov@example.com"},
            {"name": "Смирнова Анна", "role": "семинарист"},
            {"name": ""},  # пустая строка редактора
        ]
    }
    cleaned = validate_values(DEFS, values)
    assert [c["name"] for c in cleaned["teachers"]] == ["Иванов Пётр Сергеевич", "Смирнова Анна"]


def test_single_value_field_rejects_list():
    with pytest.raises(FieldError, match="одно значение"):
        validate_values([CONTROL], {"control_form": ["Экзамен"]})


def test_area_ref():
    a = uuid.uuid4()
    d = FieldDef("subj", "Предмет", FieldType.area_ref, multiple=True)
    cleaned = validate_values([d], {"subj": [str(a), str(a).upper()]})
    assert cleaned == {"subj": [str(a)]}
    assert area_refs([d], cleaned) == {str(a)}
    with pytest.raises(FieldError, match="сфера"):
        validate_values([d], {"subj": ["не-id"]})


# ---------- обязательность, неизвестные ключи, удалённые поля ----------


def test_required_missing():
    d = FieldDef("grade", "Класс", FieldType.text, required=True)
    with pytest.raises(FieldError, match="«Класс»: обязательное поле"):
        validate_values([d], {"grade": "  "})


def test_all_problems_reported_at_once():
    d = FieldDef("rate", "Ставка", FieldType.number, required=True)
    with pytest.raises(FieldError) as exc:
        validate_values([d, CONTROL], {"control_form": "нет такого"})
    assert "Ставка" in str(exc.value)
    assert "Форма контроля" in str(exc.value)


def test_unknown_keys_dropped():
    assert validate_values([CONTROL], {"control_form": "Экзамен", "hack": 1}) == {
        "control_form": "Экзамен"
    }


def test_deleted_field_keeps_stored_value_and_ignores_input():
    deleted = FieldDef("old", "Старое", FieldType.text, deleted=True, required=True)
    cleaned = validate_values(
        [deleted, CONTROL],
        {"old": "новое", "control_form": "Зачёт"},
        stored={"old": "было", "control_form": "Экзамен"},
    )
    assert cleaned == {"old": "было", "control_form": "Зачёт"}


def test_empty_definitions_and_values():
    assert validate_values([], None) == {}
    assert render_values([], {"x": 1}) == []


# ---------- описания: переименование и удаление без потери данных ----------


def test_rename_keeps_id_and_values():
    renamed = FieldDef("control_form", "Итог", FieldType.select, options=CONTROL.options)
    merged = merge_defs(DEFS, [TEACHERS, renamed, LINKS])
    assert [d.id for d in merged] == ["teachers", "control_form", "links"]
    assert render_values(merged, {"control_form": "Зачёт"}) == [("Итог", "Зачёт")]


def test_removed_field_becomes_deleted_and_hidden():
    merged = merge_defs(DEFS, [CONTROL])
    assert [(d.id, d.deleted) for d in merged] == [
        ("control_form", False),
        ("teachers", True),
        ("links", True),
    ]
    stored = {"teachers": [{"name": "Иванов"}], "control_form": "Экзамен"}
    assert render_values(merged, stored) == [("Форма контроля", "Экзамен")]
    # Поле вернули — значения снова видны
    back = merge_defs(merged, [TEACHERS, CONTROL])
    assert render_values(back, stored)[0] == ("Преподаватели", "Иванов")


def test_new_fields_get_free_ids():
    old = merge_defs(DEFS, [CONTROL])  # teachers и links — удалены, id заняты
    new = FieldDef("", "Ставка", FieldType.number)
    other = FieldDef("teachers_typo", "Класс", FieldType.text)
    merged = merge_defs(old, [CONTROL, new, other])
    assert [d.id for d in merged if not d.deleted] == ["control_form", "f1", "f2"]


def test_type_change_forbidden():
    with pytest.raises(FieldError, match="тип поля не меняется"):
        merge_defs(DEFS, [FieldDef("control_form", "Форма контроля", FieldType.text)])


def test_definition_checks():
    with pytest.raises(FieldError, match="нет вариантов"):
        merge_defs([], [FieldDef("", "Выбор", FieldType.select)])
    with pytest.raises(FieldError, match="несколько значений"):
        merge_defs([], [FieldDef("", "Число", FieldType.number, multiple=True)])
    with pytest.raises(FieldError, match="повторяются"):
        merge_defs(
            [], [FieldDef("", "Класс", FieldType.text), FieldDef("", "класс", FieldType.text)]
        )
    with pytest.raises(FieldError, match="id"):
        validate_defs([FieldDef("Bad Id", "Поле", FieldType.text)])
    validate_defs(DEFS)


def test_json_round_trip():
    merged = merge_defs(DEFS, [CONTROL])
    assert parse_defs(dump_defs(merged)) == merged


# ---------- показ ----------


def test_render_formats_and_order():
    defs = [
        FieldDef("grade", "Класс", FieldType.text),
        FieldDef("rate", "Ставка", FieldType.number, show_in_reminder=True),
        FieldDef("paid", "Оплачено", FieldType.bool),
        FieldDef("since", "С", FieldType.date),
        TEACHERS,
        LINKS,
    ]
    values = {
        "since": "2026-09-01",
        "rate": 1.5,
        "paid": False,
        "grade": "9Б",
        "teachers": [
            {"name": "Иванов", "role": "лектор", "phone": "+7 900"},
            {"role": "семинарист"},
        ],
        "links": [{"title": "", "url": "https://x.ru"}, {"title": "Курс", "url": "https://y.ru"}],
    }
    assert render_values(defs, values) == [
        ("Класс", "9Б"),
        ("Ставка", "1,5"),
        ("Оплачено", "нет"),
        ("С", "01.09.2026"),
        ("Преподаватели", "Иванов (лектор) · +7 900; семинарист"),
        ("Ссылки", "https://x.ru, Курс"),
    ]
    assert render_values(defs, values, only_reminder=True) == [("Ставка", "1,5")]


def test_render_tolerates_stale_values_and_unknown_areas():
    a = str(uuid.uuid4())
    ref = FieldDef("subj", "Предмет", FieldType.area_ref)
    # Вариант убрали из списка — значение всё равно видно
    assert render_values([CONTROL], {"control_form": "Курсовая"}) == [
        ("Форма контроля", "Курсовая")
    ]
    assert render_values([ref], {"subj": a}) == []
    assert render_values([ref], {"subj": a}, area_names={a: "Алгебра"}) == [("Предмет", "Алгебра")]

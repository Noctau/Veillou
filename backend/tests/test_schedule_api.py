from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from httpx import AsyncClient

from .conftest import PASSWORD

API = "/api/v1"

# Бывший семестр: занятия до 27.12, сессия 09.01–25.01 — паузы «Перерыв» и «Сессия»
PERIOD = {
    "name": "Осень 2026",
    "start_date": "2026-09-01",
    "end_date": "2027-01-25",
    "cycle_weeks": 2,
    "first_cycle_week": 1,
    "pauses": [
        {"from": "2026-12-28", "to": "2027-01-08", "title": "Перерыв"},
        {"from": "2027-01-09", "to": "2027-01-25", "title": "Сессия"},
    ],
}

BELLS = [
    {"number": 1, "start": "09:00", "end": "10:35"},
    {"number": 2, "start": "10:45", "end": "12:20"},
    {"number": 3, "start": "13:00", "end": "14:35"},
]

# Тип «Пара» как после миграции M17.1 (поля — по порядку: вид занятия, преподаватель)
CLASS_TYPE = {
    "name": "Пара",
    "name_plural": "Пары",
    "icon": "graduation-cap",
    "buffer_before_min": 60,
    "buffer_after_min": 60,
    "merge_buffers": True,
    "remind_before_min": 15,
    "show_now_next": True,
    "location_label": "ауд.",
    "fields": [
        {
            "label": "Вид занятия",
            "type": "select",
            "options": ["лекция", "семинар", "лаба"],
            "show_in_reminder": True,
        },
        {"label": "Преподаватель", "type": "text", "show_in_reminder": True},
    ],
}


async def make_period(client: AsyncClient, **over) -> dict:
    resp = await client.post(f"{API}/periods", json={**PERIOD, **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def make_event_type(client: AsyncClient, **over) -> dict:
    resp = await client.post(f"{API}/event-types", json={**CLASS_TYPE, **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def class_type(client: AsyncClient) -> dict:
    """Тип «Пара» пользователя; нет — создаёт."""
    for t in (await client.get(f"{API}/event-types")).json():
        if t["name"] == "Пара":
            return t
    return await make_event_type(client)


async def make_grid(client: AsyncClient, period_id: str | None, **over) -> dict:
    """Сетка «Звонки» периода; возвращает общую строку."""
    body = {
        "period_id": period_id,
        "name": "Звонки",
        "schedules": [{"weekday": None, "slots": BELLS}],
        **over,
    }
    resp = await client.put(f"{API}/slot-grids", json=body)
    assert resp.status_code == 200, resp.text
    return next(g for g in resp.json() if g["weekday"] is None)


async def make_rule(client: AsyncClient, **body: Any) -> dict:
    resp = await client.post(f"{API}/schedule-rules", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def make_class_rule(
    client: AsyncClient,
    period: dict,
    area: dict,
    *,
    weekday: int,
    slot: int | None = None,
    mask: list[int] | None = None,
    grid: dict | None = None,
    **over: Any,
) -> dict:
    """Правило «Пары» по дню недели — по слоту сетки «Звонки» или со своим временем."""
    body: dict[str, Any] = {
        "event_type_id": (await class_type(client))["id"],
        "area_id": area["id"],
        "period_id": period["id"],
        "pattern": {"kind": "weekly", "weekdays": [weekday], "cycle_weeks": mask},
        **over,
    }
    if slot is not None:
        grid = grid or await make_grid(client, period["id"])
        body |= {"slot_from": slot, "slot_grid_id": grid["id"]}
    return await make_rule(client, **body)


SUBJECT_TYPE = {
    "name": "Предмет",
    "name_plural": "Предметы",
    "icon": "graduation-cap",
    "fields": [
        {"label": "Преподаватели", "type": "contact", "multiple": True},
        {
            "label": "Форма контроля",
            "type": "select",
            "options": ["Экзамен", "Зачёт", "Дифзачёт"],
            "show_in_reminder": True,
        },
    ],
    "sections": ["schedule", "tasks", "notes", "materials", "prep"],
}


async def area_type_id(client: AsyncClient) -> str:
    """Первый тип сферы пользователя; нет ни одного — создаёт «Предмет»."""
    types = (await client.get(f"{API}/area-types")).json()
    if types:
        return str(types[0]["id"])
    resp = await client.post(f"{API}/area-types", json=SUBJECT_TYPE)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def make_area(client: AsyncClient, period_id: str | None = None, **over) -> dict:
    body = {
        "area_type_id": await area_type_id(client),
        "period_id": period_id,
        "name": "Климатология",
        "short_name": "клим",
        **over,
    }
    resp = await client.post(f"{API}/areas", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@asynccontextmanager
async def other_client(client: AsyncClient, session) -> AsyncIterator[AsyncClient]:
    from app.services.users import create_user

    await create_user(session, email="other@example.com", password=PASSWORD)
    async with AsyncClient(transport=client._transport, base_url="http://test") as other:
        await other.post(
            f"{API}/auth/login", json={"email": "other@example.com", "password": PASSWORD}
        )
        yield other


async def test_requires_auth(client: AsyncClient):
    for url in (
        "/periods",
        "/areas",
        "/schedule-rules",
        "/days-off",
        "/event-types",
        "/slot-grids",
    ):
        assert (await client.get(API + url)).status_code == 401


async def test_empty_catalogs_for_new_user(auth_client: AsyncClient):
    # Справочники не засеваются: новый пользователь начинает с нуля
    for url in ("/event-types", "/periods", "/schedule-rules", "/slot-grids"):
        assert (await auth_client.get(API + url)).json() == []


# ---------- типы занятости ----------


async def test_event_type_crud(auth_client: AsyncClient):
    t = await make_event_type(auth_client)
    assert t["key"] is None
    assert [f["label"] for f in t["fields"]] == ["Вид занятия", "Преподаватель"]
    assert t["remind_channels"] == ["push", "telegram"]

    # Без множественного числа — как единственное
    shift = await make_event_type(auth_client, name="Смена", name_plural=None, fields=[])
    assert shift["name_plural"] == "Смена"
    assert shift["position"] == t["position"] + 1

    resp = await auth_client.patch(
        f"{API}/event-types/{t['id']}", json={"remind_before_min": None, "buffer_before_min": 30}
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["remind_before_min"], resp.json()["buffer_before_min"]) == (None, 30)
    resp = await auth_client.patch(f"{API}/event-types/{t['id']}", json={"name": None})
    assert resp.status_code == 400

    # Удалённое поле пропадает из ответа, id остальных стабильны
    fields = t["fields"][1:]
    resp = await auth_client.patch(f"{API}/event-types/{t['id']}", json={"fields": fields})
    assert [f["id"] for f in resp.json()["fields"]] == [fields[0]["id"]]

    assert (await auth_client.delete(f"{API}/event-types/{t['id']}")).status_code == 204
    left = (await auth_client.get(f"{API}/event-types")).json()
    assert [x["id"] for x in left] == [shift["id"]]


async def test_event_type_validation(auth_client: AsyncClient):
    for bad in (
        {"buffer_before_min": 300},
        {"remind_before_min": -1},
        {"remind_channels": ["sms"]},
        {"icon": "rocket"},
        {"name": ""},
    ):
        resp = await auth_client.post(f"{API}/event-types", json={**CLASS_TYPE, **bad})
        assert resp.status_code == 422, bad


async def test_delete_event_type_cleans_references(auth_client: AsyncClient):
    period = await make_period(auth_client)
    area = await make_area(auth_client, period["id"])
    t = await class_type(auth_client)
    await make_class_rule(auth_client, period, area, weekday=2, slot=1)
    budget = await auth_client.post(
        f"{API}/load-budgets",
        json={"name": "Работа", "minutes_per_day": 360, "event_type_ids": [t["id"]]},
    )
    assert budget.json()["event_type_ids"] == [t["id"]]
    item = await auth_client.post(
        f"{API}/backlog", json={"title": "Сдать книги", "days_event_type_id": t["id"]}
    )
    assert item.status_code == 201, item.text

    await auth_client.delete(f"{API}/event-types/{t['id']}")
    assert (await auth_client.get(f"{API}/schedule-rules")).json() == []
    budgets = (await auth_client.get(f"{API}/load-budgets")).json()
    assert budgets[0]["event_type_ids"] == []
    [back] = (await auth_client.get(f"{API}/backlog")).json()
    assert back["days_event_type_id"] is None


# ---------- периоды ----------


async def test_period_crud(auth_client: AsyncClient):
    period = await make_period(auth_client)
    assert period["pauses"][1] == {"from": "2027-01-09", "to": "2027-01-25", "title": "Сессия"}

    resp = await auth_client.patch(f"{API}/periods/{period['id']}", json={"first_cycle_week": 2})
    assert resp.status_code == 200
    assert resp.json()["first_cycle_week"] == 2
    assert resp.json()["end_date"] == PERIOD["end_date"]

    assert [p["id"] for p in (await auth_client.get(f"{API}/periods")).json()] == [period["id"]]
    assert (await auth_client.delete(f"{API}/periods/{period['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/periods")).json() == []


async def test_period_validation(auth_client: AsyncClient):
    for bad in (
        {"end_date": "2026-08-01"},
        {"end_date": "2028-01-01"},
        {"first_cycle_week": 3},
        {"cycle_weeks": 9},
        {"pauses": [{"from": "2027-01-20", "to": "2027-02-10", "title": "x"}]},
        {"pauses": [{"from": "2026-10-10", "to": "2026-10-01"}]},
    ):
        resp = await auth_client.post(f"{API}/periods", json={**PERIOD, **bad})
        assert resp.status_code == 422, bad

    period = await make_period(auth_client)
    # PATCH валидирует итог: пауза теперь вне периода
    resp = await auth_client.patch(f"{API}/periods/{period['id']}", json={"end_date": "2026-12-31"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_data"


async def test_delete_period_cascades(auth_client: AsyncClient):
    period = await make_period(auth_client)
    area = await make_area(auth_client, period["id"])
    await make_class_rule(auth_client, period, area, weekday=2, slot=1)
    await auth_client.post(
        f"{API}/days-off",
        json={"period_id": period["id"], "date_from": "2026-11-04", "date_to": "2026-11-04"},
    )
    await auth_client.delete(f"{API}/periods/{period['id']}")
    assert (await auth_client.get(f"{API}/schedule-rules")).json() == []
    assert (await auth_client.get(f"{API}/slot-grids")).json() == []
    assert (await auth_client.get(f"{API}/days-off")).json() == []
    assert (await auth_client.get(f"{API}/areas/{area['id']}")).json()["period_id"] is None


# ---------- сетки слотов ----------


async def test_slot_grid_put_keeps_head_id(auth_client: AsyncClient):
    period = await make_period(auth_client)
    saturday = [{"number": 1, "start": "09:30", "end": "11:00"}]
    body = {
        "period_id": period["id"],
        "name": "Звонки",
        "schedules": [{"weekday": None, "slots": BELLS}, {"weekday": 6, "slots": saturday}],
    }
    resp = await auth_client.put(f"{API}/slot-grids", json=body)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [(r["weekday"], r["slots"]) for r in rows] == [(None, BELLS), (6, saturday)]
    head = rows[0]["id"]

    # Повторная замена по (период, название): общая строка та же, суббота уходит
    body["schedules"] = [{"weekday": None, "slots": BELLS[:1]}]
    rows = (await auth_client.put(f"{API}/slot-grids", json=body)).json()
    assert [(r["id"], r["slots"]) for r in rows] == [(head, BELLS[:1])]

    # Переименование по id; без общих слотов — добавляется пустая общая строка
    resp = await auth_client.put(
        f"{API}/slot-grids",
        json={
            "id": head,
            "period_id": period["id"],
            "name": "Школа",
            "schedules": [{"weekday": 1, "slots": BELLS}],
        },
    )
    rows = resp.json()
    assert [(r["id"] == head, r["weekday"], r["name"]) for r in rows] == [
        (True, None, "Школа"),
        (False, 1, "Школа"),
    ]
    listed = (await auth_client.get(f"{API}/slot-grids", params={"period_id": period["id"]})).json()
    assert len(listed) == 2


async def test_slot_grid_validation_and_conflicts(auth_client: AsyncClient):
    period = await make_period(auth_client)
    overlap = [
        {"number": 1, "start": "09:00", "end": "10:35"},
        {"number": 2, "start": "10:00", "end": "11:00"},
    ]
    for schedules in (
        [{"weekday": None, "slots": overlap}],
        [{"weekday": None, "slots": BELLS}, {"weekday": None, "slots": BELLS}],
        [{"weekday": None, "slots": [{"number": 1, "start": "10:00", "end": "09:00"}]}],
        [{"weekday": 8, "slots": BELLS}],
    ):
        body = {"period_id": period["id"], "name": "Звонки", "schedules": schedules}
        assert (await auth_client.put(f"{API}/slot-grids", json=body)).status_code == 422

    first = await make_grid(auth_client, period["id"])
    second = await make_grid(auth_client, period["id"], name="Вечер")
    resp = await auth_client.put(
        f"{API}/slot-grids",
        json={"id": second["id"], "period_id": period["id"], "name": "Звонки", "schedules": []},
    )
    assert resp.status_code == 409

    # По сетке есть правила — удалить нельзя
    area = await make_area(auth_client, period["id"])
    await make_class_rule(auth_client, period, area, weekday=2, slot=1, grid=first)
    assert (await auth_client.delete(f"{API}/slot-grids/{first['id']}")).status_code == 409
    assert (await auth_client.delete(f"{API}/slot-grids/{second['id']}")).status_code == 204


# ---------- исключения ----------


async def test_days_off(auth_client: AsyncClient):
    resp = await auth_client.post(
        f"{API}/days-off", json={"date_from": "2026-11-04", "date_to": "2026-11-04", "title": "ДНЕ"}
    )
    assert resp.status_code == 201
    day = resp.json()
    assert day["period_id"] is None
    resp = await auth_client.patch(f"{API}/days-off/{day['id']}", json={"date_to": "2026-11-01"})
    assert resp.status_code == 400
    period = await make_period(auth_client)
    resp = await auth_client.patch(f"{API}/days-off/{day['id']}", json={"period_id": period["id"]})
    assert resp.json()["period_id"] == period["id"]
    assert (await auth_client.delete(f"{API}/days-off/{day['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/days-off")).json() == []


# ---------- правила расписания ----------


async def test_schedule_rule_crud(auth_client: AsyncClient):
    period = await make_period(auth_client)
    area = await make_area(auth_client, period["id"])
    t = await class_type(auth_client)
    kind_f, teacher_f = (f["id"] for f in t["fields"])
    rule = await make_class_rule(
        auth_client,
        period,
        area,
        weekday=2,
        slot=3,
        mask=[1],
        location="1801",
        fields={kind_f: "семинар", teacher_f: "Иванов", "junk": 1},
    )
    assert rule["start_time"] is None
    assert rule["pattern"] == {"kind": "weekly", "weekdays": [2], "cycle_weeks": [1]}
    assert rule["fields"] == {kind_f: "семинар", teacher_f: "Иванов"}  # чужие ключи отброшены

    resp = await auth_client.patch(
        f"{API}/schedule-rules/{rule['id']}", json={"start_time": "18:30", "end_time": "20:00"}
    )
    assert resp.status_code == 200
    assert (resp.json()["start_time"], resp.json()["end_time"]) == ("18:30", "20:00")

    # Только начало без конца -> итог невалиден
    resp = await auth_client.patch(f"{API}/schedule-rules/{rule['id']}", json={"end_time": None})
    assert resp.status_code == 400

    listed = await auth_client.get(f"{API}/schedule-rules", params={"area_id": area["id"]})
    assert [r["id"] for r in listed.json()] == [rule["id"]]

    # Удаление сферы удаляет её правила
    await auth_client.delete(f"{API}/areas/{area['id']}")
    assert (await auth_client.get(f"{API}/schedule-rules")).json() == []


async def test_schedule_rule_patterns(auth_client: AsyncClient):
    shift = await make_event_type(auth_client, name="Смена", fields=[])
    base = {"event_type_id": shift["id"], "start_time": "20:00", "end_time": "08:00"}
    for pattern in (
        {"kind": "day_cycle", "on": 2, "off": 2, "anchor": "2026-10-12"},
        {"kind": "rrule", "rrule": "FREQ=MONTHLY;BYDAY=2TU"},
        {"kind": "once", "date": "2026-10-20"},
        {"kind": "weekly", "weekdays": [5, 1, 1]},
    ):
        rule = await make_rule(auth_client, **base, pattern=pattern)
        assert rule["pattern"]["kind"] == pattern["kind"]
    assert rule["pattern"]["weekdays"] == [1, 5]


async def test_schedule_rule_validation(auth_client: AsyncClient):
    period = await make_period(auth_client)
    area = await make_area(auth_client, period["id"])
    t = await class_type(auth_client)
    grid = await make_grid(auth_client, period["id"])
    weekly = {"kind": "weekly", "weekdays": [1]}
    base = {"event_type_id": t["id"], "area_id": area["id"], "pattern": weekly}
    for bad in (
        {},  # ни времени, ни слотов
        {"slot_from": 1},  # слот без сетки
        {"start_time": "10:00"},  # начало без конца
        {"start_time": "10:00", "end_time": "10:00"},
        {"slot_from": 2, "slot_to": 1, "slot_grid_id": grid["id"]},
        {"start_time": "10:00", "end_time": "11:00", "pattern": {**weekly, "cycle_weeks": [1]}},
        {"start_time": "10:00", "end_time": "11:00", "pattern": {"kind": "weekly", "weekdays": []}},
        {
            "start_time": "8:00",
            "end_time": "9:00",
            "pattern": {"kind": "day_cycle", "on": 0, "off": 1, "anchor": "2026-01-01"},
        },
        {
            "start_time": "10:00",
            "end_time": "11:00",
            "pattern": {"kind": "rrule", "rrule": "FREQ=HOURLY"},
        },
    ):
        resp = await auth_client.post(f"{API}/schedule-rules", json={**base, **bad})
        assert resp.status_code == 422, bad

    timed = {**base, "start_time": "10:00", "end_time": "11:00"}
    for bad in (
        # Неделя цикла больше цикла периода
        {"period_id": period["id"], "pattern": {**weekly, "cycle_weeks": [3]}},
        # «Невозможное» правило повтора
        {"pattern": {"kind": "rrule", "rrule": "FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30"}},
        # Значение вне вариантов поля
        {"fields": {t["fields"][0]["id"]: "коллоквиум"}},
    ):
        resp = await auth_client.post(f"{API}/schedule-rules", json={**timed, **bad})
        assert resp.status_code == 400, (bad, resp.text)

    # Сетка указывается общей строкой, а не переопределением дня
    rows = await auth_client.put(
        f"{API}/slot-grids",
        json={
            "period_id": period["id"],
            "name": "Звонки",
            "schedules": [{"weekday": None, "slots": BELLS}, {"weekday": 6, "slots": BELLS}],
        },
    )
    saturday = next(g["id"] for g in rows.json() if g["weekday"] == 6)
    resp = await auth_client.post(
        f"{API}/schedule-rules", json={**base, "slot_from": 1, "slot_grid_id": saturday}
    )
    assert resp.status_code == 400


async def test_other_users_data_invisible(auth_client: AsyncClient, client: AsyncClient, session):
    period = await make_period(auth_client)
    area = await make_area(auth_client, period["id"])
    t = await class_type(auth_client)
    async with other_client(client, session) as other:
        assert (await other.get(f"{API}/periods")).json() == []
        assert (await other.get(f"{API}/event-types")).json() == []
        assert (await other.get(f"{API}/areas/{area['id']}")).status_code == 404
        assert (await other.patch(f"{API}/periods/{period['id']}", json={})).status_code == 404
        assert (await other.patch(f"{API}/event-types/{t['id']}", json={})).status_code == 404
        # Нельзя повесить правило на чужие тип, период или сферу
        mine = await make_event_type(other)
        own_period = await make_period(other)
        common = {"pattern": {"kind": "weekly", "weekdays": [1]}, "start_time": "09:00"}
        common["end_time"] = "10:00"
        for body in (
            {"event_type_id": t["id"]},
            {"event_type_id": mine["id"], "area_id": area["id"]},
            {"event_type_id": mine["id"], "period_id": period["id"]},
            {"event_type_id": mine["id"], "period_id": own_period["id"], "area_id": area["id"]},
        ):
            resp = await other.post(f"{API}/schedule-rules", json={**common, **body})
            assert resp.status_code == 404, body


# ---------- события ----------


async def test_manual_event_crud(auth_client: AsyncClient):
    t = await make_event_type(auth_client)
    kind_f = t["fields"][0]["id"]
    body = {
        "title": "Консультация",
        "start": "2026-10-07T18:00:00+03:00",
        "end": "2026-10-07T19:00:00+03:00",
        "event_type_id": t["id"],
        "fields": {kind_f: "лекция"},
    }
    resp = await auth_client.post(f"{API}/events", json=body)
    assert resp.status_code == 201, resp.text
    event = resp.json()
    assert (event["kind"], event["event_type_id"], event["fields"]) == (
        "busy",
        t["id"],
        {kind_f: "лекция"},
    )
    assert event["is_fixed"] is True
    assert event["start"] == "2026-10-07T15:00:00Z"

    resp = await auth_client.patch(f"{API}/events/{event['id']}", json={"status": "done"})
    assert resp.json()["status"] == "done"
    assert resp.json()["detached"] is False  # разовое событие — не вхождение правила

    resp = await auth_client.patch(f"{API}/events/{event['id']}", json={"fields": {kind_f: "?"}})
    assert resp.status_code == 400
    # Без типа полей нет
    resp = await auth_client.patch(f"{API}/events/{event['id']}", json={"event_type_id": None})
    assert (resp.json()["event_type_id"], resp.json()["fields"]) == (None, {})

    resp = await auth_client.patch(
        f"{API}/events/{event['id']}", json={"end": "2026-10-07T17:00:00+03:00"}
    )
    assert resp.status_code == 400

    assert (await auth_client.delete(f"{API}/events/{event['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/events/{event['id']}")).status_code == 404


async def test_untyped_event_and_rejects(auth_client: AsyncClient):
    body = {"title": "Врач", "start": "2026-10-07T18:00:00Z", "end": "2026-10-07T19:00:00Z"}
    resp = await auth_client.post(f"{API}/events", json=body)
    assert resp.status_code == 201
    assert (resp.json()["kind"], resp.json()["event_type_id"]) == ("busy", None)

    naive = {**body, "start": "2026-10-07T18:00:00", "end": "2026-10-07T19:00:00"}
    assert (await auth_client.post(f"{API}/events", json=naive)).status_code == 422
    # kind руками не задаётся
    assert (
        await auth_client.post(f"{API}/events", json={**body, "kind": "busy"})
    ).status_code == 422

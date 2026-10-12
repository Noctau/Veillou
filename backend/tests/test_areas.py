"""Сферы и типы сфер (M16.2): CRUD, поля, архив, быстрый ввод."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from .test_schedule_api import API, SUBJECT_TYPE, make_area, make_period, other_client

PUPIL = {
    "name": "Ученик",
    "name_plural": "Ученики",
    "icon": "users",
    "color": "#10b981",
    "fields": [
        {"label": "Класс", "type": "text", "show_in_reminder": True},
        {"label": "Контакт родителя", "type": "contact"},
        {"label": "Ставка", "type": "number", "required": True},
    ],
    "sections": ["schedule", "tasks", "prep", "tasks"],
}


async def make_type(client: AsyncClient, body: dict | None = None) -> dict:
    resp = await client.post(f"{API}/area-types", json=body or PUPIL)
    assert resp.status_code == 201, resp.text
    return resp.json()


def ids(area_type: dict) -> dict[str, str]:
    return {f["label"]: f["id"] for f in area_type["fields"]}


async def test_requires_auth(client: AsyncClient):
    for url in ("/areas", "/area-types"):
        assert (await client.get(API + url)).status_code == 401


async def test_empty_by_default(auth_client: AsyncClient):
    assert (await auth_client.get(f"{API}/area-types")).json() == []
    assert (await auth_client.get(f"{API}/areas")).json() == []


async def test_area_type_crud(auth_client: AsyncClient):
    pupil = await make_type(auth_client)
    assert [f["id"] for f in pupil["fields"]] == ["f1", "f2", "f3"]
    assert pupil["sections"] == ["schedule", "tasks", "prep"]  # без повторов
    assert pupil["key"] is None
    other = await make_type(auth_client, SUBJECT_TYPE)
    assert other["position"] == pupil["position"] + 1

    resp = await auth_client.patch(
        f"{API}/area-types/{pupil['id']}", json={"name_plural": "Мои ученики", "icon": "star"}
    )
    assert resp.status_code == 200
    assert resp.json()["name_plural"] == "Мои ученики"
    assert len(resp.json()["fields"]) == 3

    resp = await auth_client.patch(f"{API}/area-types/{pupil['id']}", json={"name": None})
    assert resp.status_code == 400

    assert (await auth_client.delete(f"{API}/area-types/{pupil['id']}")).status_code == 204
    listed = (await auth_client.get(f"{API}/area-types")).json()
    assert [t["id"] for t in listed] == [other["id"]]


async def test_area_type_bad_fields(auth_client: AsyncClient):
    body = {**PUPIL, "fields": [{"label": "Форма", "type": "select"}]}
    resp = await auth_client.post(f"{API}/area-types", json=body)
    assert resp.status_code == 400
    assert "нет вариантов" in resp.json()["error"]["message"]
    body = {**PUPIL, "fields": [{"label": "Класс", "type": "text"}] * 2}
    resp = await auth_client.post(f"{API}/area-types", json=body)
    assert resp.status_code == 400


async def test_area_crud_with_fields(auth_client: AsyncClient):
    pupil = await make_type(auth_client)
    f = ids(pupil)
    resp = await auth_client.post(
        f"{API}/areas",
        json={
            "area_type_id": pupil["id"],
            "name": "Маша",
            "synonyms": ["машей", "маше"],
            "fields": {
                f["Класс"]: " 9Б ",
                f["Контакт родителя"]: {"name": "Ольга", "phone": "+7 900 000-00-00"},
                f["Ставка"]: "1500",
                "unknown": "отбрасывается",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    masha = resp.json()
    assert masha["fields"] == {
        f["Класс"]: "9Б",
        f["Контакт родителя"]: {"name": "Ольга", "phone": "+7 900 000-00-00"},
        f["Ставка"]: 1500,
    }
    assert masha["archived_at"] is None
    assert masha["period_id"] is None

    # Обязательное поле
    resp = await auth_client.patch(f"{API}/areas/{masha['id']}", json={"fields": {}})
    assert resp.status_code == 400
    assert "«Ставка»: обязательное поле" in resp.json()["error"]["message"]

    resp = await auth_client.patch(
        f"{API}/areas/{masha['id']}", json={"name": "Мария", "fields": {f["Ставка"]: 2000}}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Мария"
    assert resp.json()["fields"] == {f["Ставка"]: 2000}

    assert (await auth_client.get(f"{API}/areas/{masha['id']}")).json()["name"] == "Мария"
    # Тип со сферами не удаляется
    resp = await auth_client.delete(f"{API}/area-types/{pupil['id']}")
    assert resp.status_code == 409
    assert (await auth_client.delete(f"{API}/areas/{masha['id']}")).status_code == 204
    assert (await auth_client.get(f"{API}/areas/{masha['id']}")).status_code == 404
    assert (await auth_client.delete(f"{API}/area-types/{pupil['id']}")).status_code == 204


async def test_rename_and_delete_field_keep_values(auth_client: AsyncClient):
    pupil = await make_type(auth_client)
    f = ids(pupil)
    area = await make_area(auth_client, name="Маша", fields={f["Класс"]: "9Б", f["Ставка"]: 1500})

    # Переименовали «Класс», убрали «Ставку», добавили «Предмет»
    fields = [
        {**pupil["fields"][0], "label": "Класс / школа"},
        pupil["fields"][1],
        {"label": "Предмет", "type": "text"},
    ]
    resp = await auth_client.patch(f"{API}/area-types/{pupil['id']}", json={"fields": fields})
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert [(x["id"], x["label"]) for x in updated["fields"]] == [
        (f["Класс"], "Класс / школа"),
        (f["Контакт родителя"], "Контакт родителя"),
        ("f4", "Предмет"),  # f3 занят удалённой «Ставкой»
    ]

    # Правка сферы не теряет значение удалённого поля
    resp = await auth_client.patch(
        f"{API}/areas/{area['id']}", json={"fields": {f["Класс"]: "10А", "f4": "алгебра"}}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["fields"] == {f["Класс"]: "10А", f["Ставка"]: 1500, "f4": "алгебра"}

    # Поле вернули с тем же id — значение снова на месте и снова обязательно
    fields.append(pupil["fields"][2])
    resp = await auth_client.patch(f"{API}/area-types/{pupil['id']}", json={"fields": fields})
    assert [x["label"] for x in resp.json()["fields"]][-1] == "Ставка"

    # Тип поля не меняется
    bad = [{**pupil["fields"][0], "type": "number"}]
    resp = await auth_client.patch(f"{API}/area-types/{pupil['id']}", json={"fields": bad})
    assert resp.status_code == 400


async def test_area_ref_must_be_own_area(auth_client: AsyncClient, client, session):
    subject_type = await make_type(
        auth_client,
        {**PUPIL, "fields": [{"label": "Предмет", "type": "area_ref", "multiple": True}]},
    )
    algebra = await make_area(auth_client, name="Алгебра")
    resp = await auth_client.post(
        f"{API}/areas",
        json={
            "area_type_id": subject_type["id"],
            "name": "Маша",
            "fields": {"f1": [algebra["id"]]},
        },
    )
    assert resp.status_code == 201, resp.text
    masha = resp.json()
    # Ссылка на себя
    resp = await auth_client.patch(
        f"{API}/areas/{masha['id']}", json={"fields": {"f1": [masha["id"]]}}
    )
    assert resp.status_code == 400
    async with other_client(client, session) as other:
        own_type = await make_type(
            other, {**PUPIL, "fields": [{"label": "Предмет", "type": "area_ref"}]}
        )
        resp = await other.post(
            f"{API}/areas",
            json={"area_type_id": own_type["id"], "name": "X", "fields": {"f1": algebra["id"]}},
        )
        assert resp.status_code == 400


async def test_archive(auth_client: AsyncClient):
    area = await make_area(auth_client)
    resp = await auth_client.patch(f"{API}/areas/{area['id']}", json={"archived": True})
    archived_at = resp.json()["archived_at"]
    assert archived_at is not None
    # Повтор не сдвигает дату
    resp = await auth_client.patch(f"{API}/areas/{area['id']}", json={"archived": True})
    assert resp.json()["archived_at"] == archived_at
    # В списке остаётся (с датой архива)
    assert [a["id"] for a in (await auth_client.get(f"{API}/areas")).json()] == [area["id"]]
    resp = await auth_client.patch(f"{API}/areas/{area['id']}", json={"archived": False})
    assert resp.json()["archived_at"] is None


async def test_period(auth_client: AsyncClient):
    sem = await make_period(auth_client)
    area = await make_area(auth_client, sem["id"])
    other = await make_area(auth_client, name="Физика")
    listed = await auth_client.get(f"{API}/areas", params={"period_id": sem["id"]})
    assert [a["id"] for a in listed.json()] == [area["id"]]
    # Удалили период — сфера живёт без периода
    await auth_client.delete(f"{API}/periods/{sem['id']}")
    assert (await auth_client.get(f"{API}/areas/{area['id']}")).json()["period_id"] is None
    resp = await auth_client.patch(f"{API}/areas/{other['id']}", json={"period_id": sem["id"]})
    assert resp.status_code == 404


async def test_type_and_area_isolation(auth_client: AsyncClient, client, session):
    area = await make_area(auth_client)
    async with other_client(client, session) as other:
        assert (await other.get(f"{API}/areas")).json() == []
        assert (await other.get(f"{API}/areas/{area['id']}")).status_code == 404
        resp = await other.post(
            f"{API}/areas", json={"area_type_id": area["area_type_id"], "name": "X"}
        )
        assert resp.status_code == 404


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(
        "app.services.quickadd.now_utc", lambda: datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    )


async def test_quick_add_skips_archived(auth_client: AsyncClient, frozen):
    area = await make_area(auth_client, name="Алгебра", short_name="алг")
    parse = {"text": "дз алг до пт"}
    resp = await auth_client.post(f"{API}/quick-add/parse", json=parse)
    assert resp.json()["area_id"] == area["id"]
    await auth_client.patch(f"{API}/areas/{area['id']}", json={"archived": True})
    resp = await auth_client.post(f"{API}/quick-add/parse", json=parse)
    assert resp.json()["area_id"] is None


async def test_project_area(auth_client: AsyncClient):
    area = await make_area(auth_client)
    resp = await auth_client.post(
        f"{API}/projects", json={"title": "Курсовая", "area_id": area["id"]}
    )
    assert resp.status_code == 201, resp.text
    project = resp.json()
    assert project["area_id"] == area["id"]
    await auth_client.post(f"{API}/projects", json={"title": "Без сферы"})
    listed = await auth_client.get(f"{API}/projects", params={"area_id": area["id"]})
    assert [p["id"] for p in listed.json()] == [project["id"]]
    resp = await auth_client.patch(f"{API}/projects/{project['id']}", json={"area_id": None})
    assert resp.json()["area_id"] is None

from httpx import AsyncClient

from app.domain.search import HIT_END, HIT_START

from .test_notes import make_note
from .test_schedule_api import API, make_semester, make_subject, other_client
from .test_sources import make_source


async def search(client: AsyncClient, q: str, **params) -> dict:
    resp = await client.get(f"{API}/search", params={"q": q, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_requires_auth(client: AsyncClient):
    assert (await client.get(f"{API}/search", params={"q": "x"})).status_code == 401


async def test_search_notes_by_title_and_text(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    clim = await make_subject(auth_client, sem["id"])
    phys = await make_subject(auth_client, sem["id"], name="Физика атмосферы", short_name="фа")
    by_title = await make_note(auth_client, subject_id=phys["id"], title="Уравнения состояния")
    by_text = await make_note(
        auth_client,
        subject_id=clim["id"],
        title="Лекция 3",
        body_md="# Циркуляция\n\nУравнение состояния для **сухого** воздуха: $p = \\rho R T$.",
    )
    await make_note(auth_client, title="Про другое", body_md="ничего общего")

    # Морфология: «уравнение» находит «уравнения»; название весомее текста
    found = await search(auth_client, "уравнение состояния")
    assert [n["id"] for n in found["notes"]] == [by_title["id"], by_text["id"]]
    assert found["notes"][0]["snippet"] == ""  # совпало только название
    snippet = found["notes"][1]["snippet"]
    assert f"{HIT_START}Уравнение{HIT_END} {HIT_START}состояния{HIT_END}" in snippet
    assert "**" not in snippet

    # Префикс — по мере набора; «ё» = «е»
    assert [n["id"] for n in (await search(auth_client, "циркул"))["notes"]] == [by_text["id"]]
    assert [n["id"] for n in (await search(auth_client, "сухОго"))["notes"]] == [by_text["id"]]

    # Фильтр по предмету
    found = await search(auth_client, "состояния", subject_id=clim["id"])
    assert [n["id"] for n in found["notes"]] == [by_text["id"]]

    # Пустой / мусорный запрос — пусто, без ошибки
    assert await search(auth_client, "  & | !") == {"notes": [], "sources": []}
    assert (await search(auth_client, "и"))["notes"] == []  # только стоп-слово


async def test_search_reflects_edits_and_deletes(auth_client: AsyncClient):
    note = await make_note(auth_client, title="Черновик", body_md="")
    assert (await search(auth_client, "ёлка"))["notes"] == []
    await auth_client.patch(f"{API}/notes/{note['id']}", json={"body_md": "Ёлка у дома"})
    assert [n["id"] for n in (await search(auth_client, "елка"))["notes"]] == [note["id"]]
    await auth_client.delete(f"{API}/notes/{note['id']}")
    assert (await search(auth_client, "елка"))["notes"] == []


async def test_search_sources(auth_client: AsyncClient):
    sem = await make_semester(auth_client)
    subject = await make_subject(auth_client, sem["id"])
    book = await make_source(auth_client, subject["id"], author="Матвеев Л. Т.")
    found = await search(auth_client, "матвеев")
    assert [s["id"] for s in found["sources"]] == [book["id"]]
    assert found["notes"] == []
    found = await search(auth_client, "метеорологии курс")
    assert [s["id"] for s in found["sources"]] == [book["id"]]


async def test_search_isolation(auth_client: AsyncClient, session):
    await make_note(auth_client, title="Секретная лекция")
    async with other_client(auth_client, session) as other:
        assert (await search(other, "секретная"))["notes"] == []

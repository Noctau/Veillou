"""Сборки (M21.3): экспорт студентки — эталонный файл; round-trip в пустого
пользователя; повторный импорт — «ничего не меняется»; битые сборки — 422."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import time, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.time import wall_to_utc
from app.domain import bundle as dom
from app.main import app

from .snapshot_utils import Snapshots
from .student import API, TODAY, TZ, Clock, build_student

pytestmark = pytest.mark.snapshots

OTHER = "other@example.com"
PASSWORD = "correct-horse-battery"


async def _ok(resp: Any) -> Any:
    assert resp.status_code == 200, resp.text
    return resp.json()


@asynccontextmanager
async def other_client(session) -> AsyncIterator[AsyncClient]:
    """Второй, пустой пользователь: режимы «Будни» / «Выходные» и категории — как у всех
    новых, засеянных типов действий нет (иначе нейтральный тип по умолчанию остался бы
    рядом с «Самостоятельной учёбой» сборки — импорт ничего не удаляет)."""
    from sqlalchemy import update

    from app.core.time import now_utc
    from app.models import ActionType
    from app.services.users import create_user

    user = await create_user(session, email=OTHER, password=PASSWORD)
    await session.execute(
        update(ActionType).where(ActionType.user_id == user.id).values(deleted_at=now_utc())
    )
    await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"{API}/auth/login", json={"email": OTHER, "password": PASSWORD})
        assert resp.status_code == 200, resp.text
        yield client


def dump(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, ensure_ascii=False, indent=2)


async def test_student_bundle_round_trip(clock: Clock, auth_client: AsyncClient, session):
    await build_student(auth_client)
    exported = await _ok(await auth_client.get(f"{API}/config/export"))

    # Эталон: конфигурация студентки как сборка (без UUID)
    snaps = Snapshots("student")
    snaps.check("bundle.json", dump(exported))
    snaps.verify()
    # ref — читаемые названия; у студентки есть всё, кроме автозадач (их не было в Part 1)
    assert [t["ref"] for t in exported["event_types"]] == ["Пара", "Личное", "Отдых", "Экзамен"]
    assert [s for s in dom.SECTIONS if not exported[s]] == ["event_rules"]
    assert exported["settings"] == {"default_action_type": "Самостоятельная учёба"}

    # Своя же сборка — ничего не меняется
    again = await _ok(
        await auth_client.post(f"{API}/config/import", params={"dry_run": True}, json=exported)
    )
    assert (again["added"], again["changed"]) == ([], [])

    async with other_client(session) as other:
        dry = await _ok(
            await other.post(f"{API}/config/import", params={"dry_run": True}, json=exported)
        )
        assert dry["dry_run"] is True
        added = {(c["section"], c["ref"]) for c in dry["added"]}
        assert ("event_types", "Пара") in added
        assert ("areas", "Климатология") in added
        # «Будни» и «Выходные» у нового пользователя уже есть — меняются, а не добавляются
        changed = {(c["section"], c["ref"]) for c in dry["changed"]}
        assert ("day_profiles", "Будни") in changed
        # dry_run ничего не записал
        assert (await _ok(await other.get(f"{API}/config/export")))["event_types"] == []

        applied = await _ok(
            await other.post(f"{API}/config/import", params={"dry_run": False}, json=exported)
        )
        assert applied["dry_run"] is False
        assert len(applied["added"]) == len(dry["added"])

        # Round-trip: экспорт нового пользователя — тот же JSON
        mirrored = await _ok(await other.get(f"{API}/config/export"))
        assert dump(mirrored) == dump(exported)

        # Повторный импорт — ничего не меняется
        repeat = await _ok(
            await other.post(f"{API}/config/import", params={"dry_run": True}, json=exported)
        )
        assert (repeat["added"], repeat["changed"]) == ([], [])

        # Правила расписания материализованы — в календаре есть пары
        cal = await _ok(
            await other.get(
                f"{API}/calendar",
                params={
                    "from": wall_to_utc(TODAY, time(0), TZ).isoformat(),
                    "to": wall_to_utc(TODAY + timedelta(days=7), time(0), TZ).isoformat(),
                },
            )
        )
        assert any(e["kind"] == "busy" for e in cal["events"])


async def test_import_changes_by_name_and_keeps_the_rest(auth_client: AsyncClient):
    """Совпало по названию — обновляется; чего нет в сборке — остаётся."""
    resp = await auth_client.post(
        f"{API}/event-types", json={"name": "Смена", "buffer_before_min": 10}
    )
    assert resp.status_code == 201, resp.text
    await auth_client.post(f"{API}/event-types", json={"name": "Встреча"})
    bundle = {
        "event_types": [
            {"ref": "s", "name": "Смена", "buffer_before_min": 40, "remind_before_min": 60}
        ],
        "day_profiles": [
            {"ref": "after", "name": "После ночной", "wake": "15:00", "sleep": "23:30"}
        ],
        "day_profile_rules": [
            {"ref": "r", "profile": "after", "kind": "day_after", "event_type": "s"}
        ],
    }
    dry = await _ok(await auth_client.post(f"{API}/config/import", json=bundle))
    assert dry["dry_run"] is True  # по умолчанию — только отчёт
    [changed] = dry["changed"]
    assert (changed["ref"], set(changed["fields"])) == (
        "s",
        {"buffer_before_min", "remind_before_min"},
    )
    assert {c["ref"] for c in dry["added"]} == {"after", "r"}

    await _ok(
        await auth_client.post(f"{API}/config/import", params={"dry_run": False}, json=bundle)
    )
    types = {t["name"]: t for t in (await auth_client.get(f"{API}/event-types")).json()}
    assert set(types) == {"Смена", "Встреча"}
    assert (types["Смена"]["buffer_before_min"], types["Смена"]["remind_before_min"]) == (40, 60)
    rules = (await auth_client.get(f"{API}/day-profile-rules")).json()
    assert any(
        r["kind"] == "day_after" and r["event_type_id"] == types["Смена"]["id"] for r in rules
    )


@pytest.mark.parametrize(
    ("bundle", "message"),
    [
        ({"areas": [{"ref": "a", "area_type": "нет", "name": "Маша"}]}, "неизвестный 'нет'"),
        (
            {
                "categories": [
                    {"ref": "x", "name": "А", "color": "#000000"},
                    {"ref": "x", "name": "Б", "color": "#000000"},
                ]
            },
            "повторяются ref x",
        ),
        ({"settings": {"default_action_type": "нет"}}, "settings"),
    ],
)
async def test_broken_bundle_rejected(auth_client: AsyncClient, bundle, message):
    resp = await auth_client.post(f"{API}/config/import", json=bundle)
    assert resp.status_code in (400, 422), resp.text
    assert message in resp.text


async def test_invalid_item_rejected_without_partial_import(auth_client: AsyncClient):
    """Кирпич не проходит проверку `*Create` — ничего не записано."""
    bundle = {
        "event_types": [{"ref": "s", "name": "Смена"}],
        "periods": [
            {"ref": "p", "name": "Плохой", "start_date": "2026-10-10", "end_date": "2026-09-01"}
        ],
    }
    resp = await auth_client.post(f"{API}/config/import", params={"dry_run": False}, json=bundle)
    assert resp.status_code in (400, 422), resp.text
    assert "Конец периода раньше начала" in resp.text
    assert (await auth_client.get(f"{API}/event-types")).json() == []

"""M18: режимы дня — API, правила, «сегодня выходной» и сценарий 2 (смены 2/2)."""

from datetime import date, datetime, time, timedelta

from httpx import AsyncClient

from app.core.time import get_tz, now_utc, wall_to_utc
from app.domain.enums import EventKind

from .test_replan import call, task_with_steps
from .test_schedule_api import other_client

API = "/api/v1"
TZ = get_tz("Europe/Moscow")
TODAY = now_utc().astimezone(TZ).date()
# Ближайший понедельник не раньше чем послезавтра
MON = TODAY + timedelta(days=2 + (7 - (TODAY + timedelta(days=2)).weekday()) % 7)
TUE, WED, THU = (MON + timedelta(days=i) for i in range(1, 4))


def at(d: date, h: int, m: int = 0) -> datetime:
    return wall_to_utc(d, time(h, m), TZ)


async def _ok(resp, *codes: int):
    assert resp.status_code in (codes or (200, 201)), resp.text
    return resp.json() if resp.status_code != 204 else None


async def profiles(c: AsyncClient) -> list[dict]:
    return await _ok(await c.get(f"{API}/day-profiles"))


async def days(c: AsyncClient, start: date, end: date) -> dict[date, dict]:
    rows = await _ok(
        await c.get(f"{API}/day-profiles/days", params={"start": str(start), "end": str(end)})
    )
    return {date.fromisoformat(r["date"]): r for r in rows}


# ---------- сид и CRUD ----------


async def test_new_user_gets_weekdays_and_weekends(auth_client):
    ps = await profiles(auth_client)
    assert [(p["key"], p["name"], p["wake"], p["sleep"]) for p in ps] == [
        ("weekdays", "Будни", "07:30", "23:30"),
        ("weekends", "Выходные", "07:30", "23:30"),
    ]
    assert ps[0]["work_windows"] == [{"start": "09:00", "end": "21:00"}]
    assert ps[0]["lunch"] == {"start": "13:00", "end": "14:00"}
    assert ps[1]["rest_halfday_ok"] is True
    rules = await _ok(await auth_client.get(f"{API}/day-profile-rules"))
    assert [(r["kind"], r["weekdays"]) for r in rules] == [
        ("weekdays", [1, 2, 3, 4, 5]),
        ("weekdays", [6, 7]),
    ]
    got = await days(auth_client, MON, MON + timedelta(days=6))
    assert [got[MON + timedelta(days=i)]["name"] for i in range(7)] == ["Будни"] * 5 + [
        "Выходные"
    ] * 2


async def test_create_update_delete_profile(auth_client):
    p = await _ok(
        await auth_client.post(
            f"{API}/day-profiles",
            json={
                "name": "После ночной",
                "wake": "15:00",
                "sleep": "23:30",
                "lunch": None,
                "work_windows": [{"start": "16:00", "end": "22:00"}],
            },
        )
    )
    assert (p["position"], p["lunch"], p["key"]) == (2, None, None)
    p = await _ok(
        await auth_client.patch(
            f"{API}/day-profiles/{p['id']}",
            json={"lunch": {"start": "17:00", "end": "17:30"}, "rest_evening_ok": False},
        )
    )
    assert p["lunch"] == {"start": "17:00", "end": "17:30"}
    assert p["wake"] == "15:00"
    # Подъём = отбой — ошибка, режим не меняется
    resp = await auth_client.patch(f"{API}/day-profiles/{p['id']}", json={"wake": "23:30"})
    assert resp.status_code == 400
    rule = await _ok(
        await auth_client.post(
            f"{API}/day-profile-rules",
            json={"profile_id": p["id"], "kind": "dates", "date_from": str(TUE)},
        )
    )
    assert rule["date_to"] == str(TUE)
    assert (await days(auth_client, TUE, TUE))[TUE]["name"] == "После ночной"
    await _ok(await auth_client.delete(f"{API}/day-profiles/{p['id']}"), 204)
    assert (await days(auth_client, TUE, TUE))[TUE]["name"] == "Будни"
    rules = await _ok(await auth_client.get(f"{API}/day-profile-rules"))
    assert all(r["kind"] == "weekdays" for r in rules)


async def test_rule_validation(auth_client):
    pid = (await profiles(auth_client))[0]["id"]
    for body in (
        {"profile_id": pid, "kind": "dates"},
        {"profile_id": pid, "kind": "dates", "date_from": str(TUE), "date_to": str(MON)},
        {"profile_id": pid, "kind": "event_day"},
        {"profile_id": pid, "kind": "weekdays", "weekdays": []},
        {"profile_id": pid, "kind": "weekdays", "weekdays": [8]},
    ):
        resp = await auth_client.post(f"{API}/day-profile-rules", json=body)
        assert resp.status_code == 422, body
    resp = await auth_client.post(
        f"{API}/day-profile-rules",
        json={"profile_id": pid, "kind": "day_after", "event_type_id": pid},
    )
    assert resp.status_code == 404


async def test_without_profiles_builtin_defaults(auth_client):
    for p in await profiles(auth_client):
        await _ok(await auth_client.delete(f"{API}/day-profiles/{p['id']}"), 204)
    got = await days(auth_client, MON, MON + timedelta(days=6))
    assert (got[MON]["profile_id"], got[MON]["name"]) == (None, "Будни")
    assert got[MON + timedelta(days=6)]["name"] == "Выходные"


async def test_set_day_one_tap(auth_client):
    weekends = (await profiles(auth_client))[1]
    url = f"{API}/day-profiles/days/{TUE}"
    day = await _ok(await auth_client.put(url, json={"profile_id": weekends["id"]}))
    assert day == {
        "date": str(TUE),
        "profile_id": weekends["id"],
        "name": "Выходные",
        "pinned": True,
    }
    # Повторное касание заменяет правило, а не копит
    await _ok(await auth_client.put(url, json={"profile_id": weekends["id"]}))
    rules = await _ok(await auth_client.get(f"{API}/day-profile-rules"))
    assert sum(r["kind"] == "dates" for r in rules) == 1
    day = await _ok(await auth_client.put(url, json={"profile_id": None}))
    assert (day["name"], day["pinned"]) == ("Будни", False)


async def test_profiles_are_per_user(auth_client, session):
    mine = (await profiles(auth_client))[0]
    async with other_client(auth_client, session) as other:
        resp = await other.patch(f"{API}/day-profiles/{mine['id']}", json={"name": "x"})
        assert resp.status_code == 404
        resp = await other.put(f"{API}/day-profiles/days/{TUE}", json={"profile_id": mine["id"]})
        assert resp.status_code == 404
        assert len(await profiles(other)) == 2


# ---------- сценарий 2: смены 2/2 с ночными ----------


async def _nurse(c: AsyncClient) -> dict:
    shift = await _ok(
        await c.post(
            f"{API}/event-types",
            json={
                "name": "Смена",
                "name_plural": "Смены",
                "buffer_before_min": 40,
                "buffer_after_min": 40,
                "remind_before_min": 60,
            },
        )
    )
    # 2/2 «день — ночь — отсыпной — выходной»: дневные с понедельника, ночные со вторника
    for anchor, start, end in ((MON, "08:00", "20:00"), (TUE, "20:00", "08:00")):
        await _ok(
            await c.post(
                f"{API}/schedule-rules",
                json={
                    "event_type_id": shift["id"],
                    "pattern": {"kind": "day_cycle", "on": 1, "off": 3, "anchor": str(anchor)},
                    "start_time": start,
                    "end_time": end,
                    "valid_from": str(MON),
                },
            )
        )
    on_shift = await _ok(
        await c.post(
            f"{API}/day-profiles",
            json={"name": "Смена", "wake": "06:30", "sleep": "23:00", "work_windows": []},
        )
    )
    after = await _ok(
        await c.post(
            f"{API}/day-profiles",
            json={
                "name": "После ночной",
                "wake": "15:00",
                "sleep": "23:30",
                "work_windows": [{"start": "08:00", "end": "22:00"}],
                "rest_evening_ok": False,
            },
        )
    )
    for profile, kind in ((on_shift, "event_day"), (after, "day_after")):
        await _ok(
            await c.post(
                f"{API}/day-profile-rules",
                json={"profile_id": profile["id"], "kind": kind, "event_type_id": shift["id"]},
            )
        )
    return shift


async def test_scenario_2_shifts_and_after_night(auth_client, user):
    await _nurse(auth_client)
    got = await days(auth_client, MON, MON + timedelta(days=4))
    assert [got[MON + timedelta(days=i)]["name"] for i in range(5)] == [
        "Смена",
        "Смена",
        "После ночной",
        "Будни",
        "Смена",
    ]
    for _ in range(4):
        await task_with_steps(auth_client, 60, 60, deadline=at(THU, 22))

    snap = await call(user, "snapshot", now=at(MON, 6))
    wed = next(d for d in snap.inp.days if d.date == WED)
    assert wed.wake == at(WED, 15)
    shift_days = [d for d in snap.inp.days if d.date in (MON, TUE)]
    assert all(d.work == () for d in shift_days)

    rev = await call(user, "preview", now=at(MON, 6))
    assert rev is not None
    placed = [
        (datetime.fromisoformat(o["after"]["start"]), datetime.fromisoformat(o["after"]["end"]))
        for o in rev.ops
        if o["op"] == "add" and o["kind"] == EventKind.subtask
    ]
    assert placed
    for start, end in placed:
        # не в смену с дорогой и не в «отсыпной» до 15:00
        assert not (start < at(MON, 20, 40) and end > at(MON, 7, 20)), start
        assert not (start < at(WED, 8, 40) and end > at(TUE, 19, 20)), start
        assert not (start < at(WED, 15) and end > at(WED, 8)), start

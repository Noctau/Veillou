"""ИИ-настройка (M21.4): нормализация черновика в сборку и сценарий 7 —
«работаю в кофейне 2/2 с 8 до 20, учусь заочно, по субботам веду кружок рисования»
→ черновик → правка → «Применить» = импорт."""

import json
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient

from app.ai import set_provider
from app.ai.fake import FakeProvider
from app.domain import bundle as dom

from .test_ai import job_result, run_ai_jobs

API = "/api/v1"
TODAY = date(2026, 10, 12)
COFFEE = "работаю в кофейне 2/2 с 8 до 20, учусь заочно, по субботам веду кружок рисования"


@pytest.fixture
def fake():
    provider = FakeProvider()
    set_provider(provider)
    yield provider
    set_provider(None)


def rule(**over: Any) -> dict[str, Any]:
    base = {
        "event_type": "Смена",
        "area": "",
        "title": "",
        "pattern": "weekly",
        "weekdays": [],
        "on_days": 0,
        "off_days": 0,
        "anchor": "",
        "date": "",
        "start": "08:00",
        "end": "20:00",
    }
    return {**base, **over}


def profile(**over: Any) -> dict[str, Any]:
    base = {
        "name": "Смена",
        "wake": "06:30",
        "sleep": "22:30",
        "work_start": "",
        "work_end": "",
        "weekdays": [],
        "on_event_type": "",
        "after_event_type": "",
    }
    return {**base, **over}


def coffee_answer(**over: Any) -> dict[str, Any]:
    data = {
        "about": "Бариста в кофейне 2/2, учусь заочно, веду кружок рисования.",
        "area_types": [{"name": "Работа", "name_plural": "Работа", "fields": []}],
        "areas": [
            {"name": "Кофейня", "type": "Работа"},
            {"name": "Кружок рисования", "type": "Работа"},
        ],
        "event_types": [
            {
                "name": "Смена",
                "name_plural": "Смены",
                "travel_min": 30,
                "remind_min": 60,
                "is_rest": False,
                "show_now_next": True,
            },
            {
                "name": "Кружок",
                "name_plural": "Кружки",
                "travel_min": 999,
                "remind_min": 30,
                "is_rest": False,
                "show_now_next": True,
            },
        ],
        "rules": [
            rule(area="Кофейня", pattern="shifts", on_days=2, off_days=2),
            rule(event_type="Кружок", area="Кружок рисования", weekdays=["сб"], start="11:00",
                 end="13:00"),
            # Повтор и мусор — выкидываются
            rule(event_type="Кружок", area="Кружок рисования", weekdays=["сб"], start="11:00",
                 end="13:00"),
            rule(event_type="Нет такого", weekdays=["пн"]),
            rule(event_type="Кружок", weekdays=[]),
        ],
        "day_profiles": [profile(on_event_type="Смена", work_start="20:30", work_end="22:00")],
        "budgets": [
            {
                "name": "Учёба",
                "minutes_per_day": 5,
                "event_types": ["Нет такого"],
                "action_types": ["Сосредоточенная работа"],
            }
        ],
        "task_types": [{"name": "Контрольная", "synonyms": ["контрольная", "контрольная"]}],
        "warning": "Уточните дату первой смены",
    }  # fmt: skip
    data.update(over)
    return data


EMPTY: dict[str, Any] = {"version": 1}


# ---------- нормализация (чистая) ----------


def test_normalize_coffee_draft():
    result = dom.normalize_setup(coffee_answer(), EMPTY, TODAY)
    b = result.bundle
    dom.check_refs(b)
    [shift, club] = b["schedule_rules"]
    assert shift["pattern"] == {"kind": "day_cycle", "on": 2, "off": 2, "anchor": "2026-10-12"}
    assert (shift["start_time"], shift["end_time"], shift["area"]) == ("08:00", "20:00", "Кофейня")
    assert club["pattern"] == {"kind": "weekly", "weekdays": [6], "cycle_weeks": None}
    types = {t["name"]: t for t in b["event_types"]}
    assert types["Кружок"]["buffer_before_min"] == 240  # границы
    assert types["Смена"]["remind_before_min"] == 60
    [rule_] = b["day_profile_rules"]
    assert (rule_["kind"], rule_["event_type"]) == ("event_day", "Смена")
    assert b["day_profiles"][0]["work_windows"] == [{"start": "20:30", "end": "22:00"}]
    [budget] = b["budgets"]
    assert (budget["minutes_per_day"], budget["event_types"]) == (15, [])
    # Ссылка на тип действия, которого в черновике нет и в настройке нет, — пропущена
    assert budget["action_types"] == []
    assert b["task_types"] == [
        {"ref": "Контрольная", "name": "Контрольная", "synonyms": ["контрольная"]}
    ]
    assert result.warnings[0] == "Уточните дату первой смены"
    text = "\n".join(result.warnings)
    assert "нет типа занятости" in text
    assert "не указаны дни недели" in text
    assert "дата первой смены не указана" in text
    assert result.about.startswith("Бариста")


def test_normalize_borrows_existing_bricks():
    """Ссылка на кирпич текущей настройки — он копируется в сборку (при импорте «уже есть»)."""
    current = {
        "version": 1,
        "categories": [{"ref": "Работа", "name": "Работа", "color": "#000000", "icon": "tag"}],
        "action_types": [
            {
                "ref": "Фокус",
                "name": "Фокус",
                "windows": [{"weekdays": [1], "start": "09:00", "end": "18:00"}],
                "category": "Работа",
                "prefer_morning": False,
                "synonyms": [],
            }
        ],
        "event_types": [{"ref": "Смена", "name": "Смена"}],
    }
    draft = coffee_answer(
        event_types=[],
        budgets=[
            {"name": "Работа", "minutes_per_day": 360, "event_types": ["смена"],
             "action_types": ["фокус"]}
        ],
    )  # fmt: skip
    b = dom.normalize_setup(draft, current, TODAY).bundle
    dom.check_refs(b)
    assert [t["name"] for t in b["event_types"]] == ["Смена"]
    assert [a["ref"] for a in b["action_types"]] == ["Фокус"]
    assert b["action_types"][0]["category"] == "Работа"  # с собой — и категория
    assert b["budgets"][0]["event_types"] == ["Смена"]
    # Для импорта заимствованное — «уже есть»
    diff = dom.diff(current, b)
    assert {(i.section, i.status) for i in diff.items if i.section == "action_types"} == {
        ("action_types", "skipped")
    }


def test_overlapping_weekly_rules_warn():
    draft = coffee_answer(
        rules=[
            rule(event_type="Кружок", weekdays=["сб"], start="11:00", end="13:00"),
            rule(event_type="Смена", weekdays=[6, 7], start="12:00", end="20:00"),
        ]
    )
    warnings = dom.normalize_setup(draft, EMPTY, TODAY).warnings
    assert any("пересекаются" in w for w in warnings)


# ---------- сценарий 7 ----------


async def test_scenario_7_setup_review_apply(auth_client: AsyncClient, fake):
    resp = await auth_client.post(f"{API}/config/ai-setup", json={"text": COFFEE})
    assert resp.status_code == 202, resp.text
    fake.push(json.dumps(coffee_answer(), ensure_ascii=False))
    await run_ai_jobs()
    job = await job_result(auth_client, resp.json()["job_id"])
    assert job["status"] == "done", job
    draft = job["result"]
    assert draft["type"] == "setup"
    user = fake.calls[0][0][1].content
    assert "Типы действий: Связь с людьми" in user  # текущая настройка — контекст
    assert COFFEE in user
    added = {(c["section"], c["ref"]) for c in draft["preview"]["added"]}
    assert ("schedule_rules", "Кофейня 1") in added
    assert ("event_types", "Смена") in added
    # До «Применить» ничего не создано
    assert (await auth_client.get(f"{API}/event-types")).json() == []

    # Правка на экране проверки: выкинули лимит, сдвинули начало смен
    bundle = draft["bundle"]
    bundle["budgets"] = []
    bundle["schedule_rules"][0]["start_time"] = "09:00"
    applied = await auth_client.post(f"{API}/config/import", params={"dry_run": False}, json=bundle)
    assert applied.status_code == 200, applied.text
    rules = (await auth_client.get(f"{API}/schedule-rules")).json()
    assert sorted(r["start_time"] for r in rules) == ["09:00", "11:00"]
    assert (await auth_client.get(f"{API}/load-budgets")).json() == []

    # «Заново с комментарием»: прошлый черновик и комментарий — в промпте
    resp = await auth_client.post(
        f"{API}/config/ai-setup",
        json={"text": COFFEE, "comment": "смены с 9", "previous": ["Смена: 2 через 2, 08:00"]},
    )
    fake.push(json.dumps(coffee_answer(), ensure_ascii=False))
    await run_ai_jobs()
    last = fake.calls[-1][0][-1].content
    assert "смены с 9" in last
    assert "Смена: 2 через 2" in last
    # Повторный черновик знает, что уже есть: «Смена» — не добавляется заново
    again = (await job_result(auth_client, resp.json()["job_id"]))["result"]
    assert ("event_types", "Смена") not in {
        (c["section"], c["ref"]) for c in again["preview"]["added"]
    }


def test_area_type_named_instead_of_area():
    """Модель назвала тип сферы вместо сферы: единственная сфера этого типа."""
    draft = coffee_answer(
        areas=[{"name": "Кофейня", "type": "Работа"}],
        rules=[rule(area="работа", pattern="shifts", on_days=2, off_days=2, anchor="2026-10-14")],
    )
    result = dom.normalize_setup(draft, EMPTY, TODAY)
    [shift] = result.bundle["schedule_rules"]
    assert shift["area"] == "Кофейня"
    assert shift["pattern"]["anchor"] == "2026-10-14"
    assert not any("первой смены не указана" in w for w in result.warnings)

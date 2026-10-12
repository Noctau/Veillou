"""M18 contract: настройки дня → режимы дня

- `settings.work_hours`, `settings.sleep`, `settings.lunch` удаляются (они в
  «Будни» / «Выходные», M18.1);
- `settings.schedule.morning_digest` (настенное время) → `morning_digest_after_wake_min`
  (минут после подъёма), `settings.schedule.evening_review` →
  `evening_review_before_sleep_min` (минут до отбоя) — по сну Part 1, так что время
  сводки и разбора у пользователя не меняется. Новые значения пишутся, только если
  отличаются от новых дефолтов (30 и 120).

Downgrade собирает старые ключи из режимов «Будни» (сон, обед, будни) и «Выходные»
(рабочие часы выходных) — только интервалы, которые отличаются от дефолтов Part 1.

Revision ID: 8e1f7a2b4c65
Revises: 7d0e6f1a3b54
Create Date: 2026-10-14 10:10:00.000000

"""

import json
from collections.abc import Sequence
from datetime import time
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8e1f7a2b4c65"
down_revision: str | Sequence[str] | None = "7d0e6f1a3b54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DIGEST, OLD_REVIEW = "08:00", "21:30"
NEW_DIGEST_AFTER, NEW_REVIEW_BEFORE = 30, 120
OLD_DEFAULTS: dict[str, Any] = {
    "sleep": {"start": "23:30", "end": "07:30"},
    "lunch": {"start": "13:00", "end": "14:00"},
    "work_hours": {
        "weekdays": {"start": "09:00", "end": "21:00"},
        "weekends": {"start": "11:00", "end": "19:00"},
    },
}
DAY = 24 * 60


def _minutes(raw: str) -> int:
    t = time.fromisoformat(raw)
    return t.hour * 60 + t.minute


def _hhmm(minutes: int) -> str:
    minutes %= DAY
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _signed(delta: int) -> int:
    """Разница по кругу суток → (-720, 720]."""
    delta %= DAY
    return delta - DAY if delta > DAY // 2 else delta


def new_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(settings or {})
    sleep = {**OLD_DEFAULTS["sleep"], **(result.get("sleep") or {})}
    schedule = dict(result.get("schedule") or {})
    digest = schedule.pop("morning_digest", OLD_DIGEST)
    review = schedule.pop("evening_review", OLD_REVIEW)
    after_wake = _signed(_minutes(digest) - _minutes(sleep["end"]))
    before_sleep = _signed(_minutes(sleep["start"]) - _minutes(review))
    if after_wake != NEW_DIGEST_AFTER:
        schedule["morning_digest_after_wake_min"] = after_wake
    if before_sleep != NEW_REVIEW_BEFORE:
        schedule["evening_review_before_sleep_min"] = before_sleep
    for key in ("work_hours", "sleep", "lunch"):
        result.pop(key, None)
    if schedule:
        result["schedule"] = schedule
    else:
        result.pop("schedule", None)
    return result


def _differs(value: dict[str, str], default: dict[str, str]) -> dict[str, str]:
    """Интервал целиком, если он не дефолтный (форма настроек Part 1 сохраняла оба конца)."""
    return value if value != default else {}


def old_settings(
    settings: dict[str, Any] | None,
    weekdays: dict[str, Any] | None,
    weekends: dict[str, Any] | None,
) -> dict[str, Any]:
    """Обратно: старые ключи из «Будней» и «Выходных» (только отличия от дефолтов)."""
    result = dict(settings or {})
    schedule = dict(result.get("schedule") or {})
    after_wake = schedule.pop("morning_digest_after_wake_min", NEW_DIGEST_AFTER)
    before_sleep = schedule.pop("evening_review_before_sleep_min", NEW_REVIEW_BEFORE)
    base = weekdays or weekends
    if base is not None:
        sleep = {"start": base["sleep"], "end": base["wake"]}
        if diff := _differs(sleep, OLD_DEFAULTS["sleep"]):
            result["sleep"] = diff
        if base["lunch_start"] and base["lunch_end"]:
            lunch = {"start": base["lunch_start"], "end": base["lunch_end"]}
            if diff := _differs(lunch, OLD_DEFAULTS["lunch"]):
                result["lunch"] = diff
        work: dict[str, Any] = {}
        for key, profile in (("weekdays", weekdays), ("weekends", weekends)):
            windows = (profile or {}).get("work_windows") or []
            if windows:
                window = {"start": windows[0]["start"], "end": windows[0]["end"]}
                if diff := _differs(window, OLD_DEFAULTS["work_hours"][key]):
                    work[key] = diff
        if work:
            result["work_hours"] = work
        digest = _hhmm(_minutes(base["wake"]) + after_wake)
        review = _hhmm(_minutes(base["sleep"]) - before_sleep)
        if digest != OLD_DIGEST:
            schedule["morning_digest"] = digest
        if review != OLD_REVIEW:
            schedule["evening_review"] = review
    if schedule:
        result["schedule"] = schedule
    else:
        result.pop("schedule", None)
    return result


def upgrade() -> None:
    bind = op.get_bind()
    update = sa.text("UPDATE users SET settings = CAST(:settings AS jsonb) WHERE id = :id")
    for user in bind.execute(sa.text("SELECT id, settings FROM users")).all():
        settings = new_settings(user.settings)
        if settings != (user.settings or {}):
            bind.execute(
                update, {"id": user.id, "settings": json.dumps(settings, ensure_ascii=False)}
            )


def downgrade() -> None:
    bind = op.get_bind()
    update = sa.text("UPDATE users SET settings = CAST(:settings AS jsonb) WHERE id = :id")
    rows = bind.execute(
        sa.text(
            "SELECT user_id, key, to_char(wake, 'HH24:MI') AS wake, "
            "to_char(sleep, 'HH24:MI') AS sleep, to_char(lunch_start, 'HH24:MI') AS lunch_start, "
            "to_char(lunch_end, 'HH24:MI') AS lunch_end, work_windows FROM day_profiles "
            "WHERE deleted_at IS NULL AND key IN ('weekdays', 'weekends')"
        )
    ).all()
    profiles: dict[Any, dict[str, dict[str, Any]]] = {}
    for r in rows:
        profiles.setdefault(r.user_id, {})[r.key] = dict(r._mapping)
    for user in bind.execute(sa.text("SELECT id, settings FROM users")).all():
        own = profiles.get(user.id, {})
        settings = old_settings(user.settings, own.get("weekdays"), own.get("weekends"))
        if settings != (user.settings or {}):
            bind.execute(
                update, {"id": user.id, "settings": json.dumps(settings, ensure_ascii=False)}
            )

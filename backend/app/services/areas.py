"""Сферы и типы сфер (Part 2, M16.2): CRUD, поля (domain/fields.py) и выбор
сфер для быстрого ввода."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, InvalidDataError
from app.core.time import get_tz, now_utc
from app.domain.fields import FieldError, area_refs, dump_defs, merge_defs, parse_defs
from app.domain.fields import validate_values as clean_values
from app.domain.quickparse import AreaRef
from app.models import Area, AreaType, ClassRule, Semester, User
from app.schemas.area import AreaCreate, AreaTypeCreate, AreaTypeUpdate, AreaUpdate
from app.services.base import UserScopedRepository
from app.services.schedule_sync import SeriesSync


class AreaTypeRepo(UserScopedRepository[AreaType]):
    model = AreaType
    not_found_message = "Тип сферы не найден"


class AreaRepo(UserScopedRepository[Area]):
    model = Area
    not_found_message = "Сфера не найдена"


class _PeriodRepo(UserScopedRepository[Semester]):
    model = Semester
    not_found_message = "Период не найден"


class _RuleRepo(UserScopedRepository[ClassRule]):
    model = ClassRule


def _sections(values: list[Any]) -> list[str]:
    return [str(getattr(v, "value", v)) for v in values]


async def area_refs_for_parse(db: AsyncSession, user: User, today: date) -> list[AreaRef]:
    """Сферы для быстрого ввода и ИИ: не в архиве, в активном периоде или без периода.
    Если таких нет — все неархивные: одинаковые названия из прошлых периодов не делают
    разбор неоднозначным, пока есть текущие."""
    active_periods = select(Semester.id).where(
        Semester.user_id == user.id,
        Semester.deleted_at.is_(None),
        Semester.start_date <= today,
        or_(
            Semester.session_end >= today,
            Semester.session_end.is_(None) & (Semester.classes_end >= today),
        ),
    )
    base = select(Area).where(
        Area.user_id == user.id, Area.deleted_at.is_(None), Area.archived_at.is_(None)
    )
    areas = list(
        await db.scalars(
            base.where(or_(Area.period_id.in_(active_periods), Area.period_id.is_(None)))
        )
    )
    if not areas:
        areas = list(await db.scalars(base))
    return [
        AreaRef(a.id, tuple(n for n in (a.name, a.short_name, *a.synonyms) if n)) for a in areas
    ]


class AreaService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user_id = user.id
        self.types = AreaTypeRepo(db, user.id)
        self.areas = AreaRepo(db, user.id)
        self.periods = _PeriodRepo(db, user.id)
        self.rules = _RuleRepo(db, user.id)
        self.sync = SeriesSync(db, user.id, get_tz(user.timezone))

    # ---------- типы сфер ----------

    async def list_types(self) -> list[AreaType]:
        return await self.types.find_all(order_by=[AreaType.position, AreaType.created_at])

    async def create_type(self, data: AreaTypeCreate) -> AreaType:
        try:
            defs = merge_defs([], [f.to_def() for f in data.fields])
        except FieldError as exc:
            raise InvalidDataError(str(exc)) from exc
        position = await self.db.scalar(
            select(func.coalesce(func.max(AreaType.position) + 1, 0)).where(
                AreaType.user_id == self.user_id, AreaType.deleted_at.is_(None)
            )
        )
        area_type = AreaType(
            key=None,
            name=data.name,
            name_plural=data.name_plural,
            icon=data.icon,
            color=data.color,
            fields=dump_defs(defs),
            sections=_sections(data.sections),
            position=position or 0,
        )
        self.types.add(area_type)
        await self.db.commit()
        return area_type

    async def update_type(self, id: uuid.UUID, patch: AreaTypeUpdate) -> AreaType:
        area_type = await self.types.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name, value in changes.items():
            if value is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if patch.fields is not None:
            try:
                defs = merge_defs(parse_defs(area_type.fields), [f.to_def() for f in patch.fields])
            except FieldError as exc:
                raise InvalidDataError(str(exc)) from exc
            changes["fields"] = dump_defs(defs)
        if patch.sections is not None:
            changes["sections"] = _sections(patch.sections)
        for name, value in changes.items():
            setattr(area_type, name, value)
        await self.db.commit()
        return area_type

    async def delete_type(self, id: uuid.UUID) -> None:
        """Тип с живыми сферами не удаляется — 409 (сферы нельзя оставить без типа)."""
        area_type = await self.types.get_or_404(id)
        if await self.areas.find_all(Area.area_type_id == id, limit=1):
            raise ConflictError(
                "У этого типа есть сферы — сначала удалите их", code="area_type_in_use"
            )
        self.types.soft_delete(area_type)
        await self.db.commit()

    # ---------- сферы ----------

    async def list_areas(self, period_id: uuid.UUID | None = None) -> list[Area]:
        where = [Area.period_id == period_id] if period_id else []
        return await self.areas.find_all(*where, order_by=[Area.name])

    async def get_area(self, id: uuid.UUID) -> Area:
        return await self.areas.get_or_404(id)

    async def _clean_fields(
        self,
        area_type: AreaType,
        values: dict[str, Any],
        stored: dict[str, Any] | None = None,
        self_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        defs = parse_defs(area_type.fields)
        try:
            cleaned = clean_values(defs, values, stored=stored)
        except FieldError as exc:
            raise InvalidDataError(str(exc)) from exc
        if refs := area_refs(defs, cleaned):
            ids = {uuid.UUID(r) for r in refs}
            found = {a.id for a in await self.areas.find_all(Area.id.in_(ids))}
            if ids - found or (self_id is not None and self_id in ids):
                raise InvalidDataError("Ссылка на несуществующую сферу")
        return cleaned

    async def create_area(self, data: AreaCreate) -> Area:
        area_type = await self.types.get_or_404(data.area_type_id)
        if data.period_id:
            await self.periods.get_or_404(data.period_id)
        area = Area(
            area_type_id=area_type.id,
            period_id=data.period_id,
            name=data.name,
            short_name=data.short_name or None,
            color=data.color,
            synonyms=data.synonyms,
            fields=await self._clean_fields(area_type, data.fields),
            notes=data.notes,
        )
        self.areas.add(area)
        await self.db.commit()
        return area

    async def update_area(self, id: uuid.UUID, patch: AreaUpdate) -> Area:
        area = await self.areas.get_or_404(id)
        changes = patch.model_dump(exclude_unset=True)
        for name in ("name", "color", "synonyms", "fields", "notes", "archived"):
            if name in changes and changes[name] is None:
                raise InvalidDataError(f"{name}: не может быть пустым")
        if changes.get("period_id") and changes["period_id"] != area.period_id:
            await self.periods.get_or_404(changes["period_id"])
        if "fields" in changes:
            area_type = await self.types.get_or_404(area.area_type_id)
            changes["fields"] = await self._clean_fields(
                area_type, changes["fields"], stored=area.fields, self_id=area.id
            )
        if "archived" in changes:
            archived = changes.pop("archived")
            if archived != (area.archived_at is not None):
                area.archived_at = now_utc() if archived else None
        if "short_name" in changes:
            changes["short_name"] = changes["short_name"] or None
        renamed = changes.keys() & {"name", "color"}
        for name, value in changes.items():
            setattr(area, name, value)
        await self.db.flush()
        if renamed:
            await self.sync.sync_area(area)
        await self.db.commit()
        return area

    async def delete_area(self, id: uuid.UUID) -> None:
        """Удаляет сферу и её правила пар (вхождения с сегодняшнего дня)."""
        area = await self.areas.get_or_404(id)
        for rule in await self.rules.find_all(ClassRule.area_id == id):
            self.rules.soft_delete(rule)
            await self.sync.remove_series(rule)
        self.areas.soft_delete(area)
        await self.db.commit()

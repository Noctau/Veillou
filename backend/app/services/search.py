"""Поиск по конспектам (название и текст) и литературе — Postgres FTS, словарь russian."""

import uuid

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notes import excerpt
from app.domain.search import HIT_END, HIT_START, build_tsquery
from app.models import Note, Source, User
from app.schemas.search import NoteHit, SearchResults
from app.services.notes import NoteService
from app.services.sources import SourceService

HEADLINE_OPTIONS = (
    f"StartSel={HIT_START}, StopSel={HIT_END}, MaxWords=24, MinWords=8, "
    'MaxFragments=2, FragmentDelimiter=" … "'
)
SNIPPET_LIMIT = 220


class SearchService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user

    async def search(
        self, text: str, *, subject_id: uuid.UUID | None = None, limit: int = 20
    ) -> SearchResults:
        tsquery = build_tsquery(text)
        if tsquery is None:
            return SearchResults(notes=[], sources=[])
        query = func.to_tsquery("russian", literal(tsquery))

        note_stmt = (
            select(
                Note,
                func.ts_headline("russian", Note.body_md, query, HEADLINE_OPTIONS),
            )
            .where(
                Note.user_id == self.user.id,
                Note.deleted_at.is_(None),
                Note.search.bool_op("@@")(query),
            )
            .order_by(func.ts_rank(Note.search, query).desc(), Note.class_date.desc().nulls_last())
            .limit(limit)
        )
        if subject_id:
            note_stmt = note_stmt.where(Note.subject_id == subject_id)
        rows = (await self.db.execute(note_stmt)).all()

        items = await NoteService(self.db, self.user).list_items([r[0] for r in rows])
        notes = []
        for item, (_, headline) in zip(items, rows, strict=True):
            hit = NoteHit(**item.model_dump())
            # Нашлось только в названии — ts_headline отдаёт начало текста без отметок
            hit.snippet = excerpt(headline, SNIPPET_LIMIT) if HIT_START in headline else ""
            notes.append(hit)

        source_stmt = (
            select(Source)
            .where(
                Source.user_id == self.user.id,
                Source.deleted_at.is_(None),
                Source.search.bool_op("@@")(query),
            )
            .order_by(func.ts_rank(Source.search, query).desc())
            .limit(limit)
        )
        if subject_id:
            source_stmt = source_stmt.where(Source.subject_id == subject_id)
        found = list(await self.db.scalars(source_stmt))
        sources = await SourceService(self.db, self.user).reads(found)
        return SearchResults(notes=notes, sources=sources)

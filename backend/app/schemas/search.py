from pydantic import Field

from app.schemas.common import ReadModel
from app.schemas.note import NoteListItem
from app.schemas.source import SourceRead


class NoteHit(NoteListItem):
    snippet: str = Field(
        default="",
        description="Фрагмент текста; совпадения обёрнуты в \\u0002…\\u0003",
    )


class SearchResults(ReadModel):
    notes: list[NoteHit]
    sources: list[SourceRead]

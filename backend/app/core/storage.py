"""Хранилище файлов. MVP — локальный диск (`settings.STORAGE_DIR`).

Файлы адресуются содержимым: ключ — sha256, так что одинаковые файлы хранятся
один раз (дедупликация). Запись идёт во временный файл с подсчётом хэша и
размера, затем атомарно переносится на место.
"""

import hashlib
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anyio

from app.core.config import settings
from app.core.exceptions import AppError

CHUNK = 1024 * 1024


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


@dataclass(frozen=True)
class StoredBlob:
    key: str
    sha256: str
    size: int


class Storage(Protocol):
    async def save(self, chunks: AsyncIterator[bytes], *, max_bytes: int) -> StoredBlob: ...

    def path(self, key: str) -> Path: ...

    def exists(self, key: str) -> bool: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: str) -> Path:
        # Ключ — только из нашего же sha256, но на всякий случай не выходим из root
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError("Некорректный ключ файла")
        return target

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    async def save(self, chunks: AsyncIterator[bytes], *, max_bytes: int) -> StoredBlob:
        tmp_dir = self.root / "tmp"
        await anyio.to_thread.run_sync(lambda: tmp_dir.mkdir(parents=True, exist_ok=True))
        tmp = tmp_dir / f"{uuid.uuid4().hex}.part"
        digest = hashlib.sha256()
        size = 0
        try:
            async with await anyio.open_file(tmp, "wb") as out:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise FileTooLargeError(f"Файл больше {max_bytes // (1024 * 1024)} МБ")
                    digest.update(chunk)
                    await out.write(chunk)
            sha = digest.hexdigest()
            key = f"{sha[:2]}/{sha[2:4]}/{sha}"
            target = self.path(key)

            def _place() -> None:
                if target.exists():
                    tmp.unlink()  # такой файл уже есть — дедупликация
                    return
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(tmp, target)

            await anyio.to_thread.run_sync(_place)
            return StoredBlob(key=key, sha256=sha, size=size)
        finally:
            if tmp.exists():
                tmp.unlink()


def get_storage() -> Storage:
    return LocalStorage(settings.STORAGE_DIR)

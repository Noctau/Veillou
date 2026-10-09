"""Логи без секретов."""

import logging
import re

_SIG = re.compile(r"(sig=)[^&\s\"]+")


class RedactSignatures(logging.Filter):
    """Подпись в ссылках /files/{id}?exp=…&sig=… — пропуск к файлу на час: в лог — без неё."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _SIG.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args
            )
        return True


def install() -> None:
    logging.getLogger("uvicorn.access").addFilter(RedactSignatures())

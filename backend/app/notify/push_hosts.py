"""Куда воркер может отправлять Web Push.

`endpoint` подписки приходит от клиента — без проверки это SSRF: воркер слал бы
POST на любой адрес (в т. ч. во внутренние сети). Разрешены только push-сервисы
браузеров; редиректы отправитель не выполняет.
"""

from urllib.parse import urlsplit

from app.core.config import settings


def push_host_allowed(endpoint: str) -> bool:
    try:
        url = urlsplit(endpoint)
        port = url.port
    except ValueError:
        return False
    host = (url.hostname or "").lower()
    if url.scheme != "https" or url.username or url.password or port not in (None, 443):
        return False
    for pattern in settings.PUSH_ALLOWED_HOSTS:
        pattern = pattern.lower()
        if pattern.startswith("*."):
            if host.endswith(pattern[1:]):
                return True
        elif host == pattern:
            return True
    return False

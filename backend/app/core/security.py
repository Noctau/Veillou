import hashlib
import hmac
import secrets

import anyio
from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()  # argon2id: ~25 мс CPU и 64 МБ памяти на хэш

# Проверяется, когда пользователь не найден: время ответа не выдаёт, есть ли такой email.
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(16))

# Длиннее не нужно, а хэшировать мегабайтные строки незачем
MAX_PASSWORD_LENGTH = 1024

# argon2 считается в потоках (не блокирует event loop) и не больше стольких сразу:
# иначе флуд логинов съест память (64 МБ на хэш) и все ядра.
MAX_CONCURRENT_HASHES = 2
_limiter: anyio.CapacityLimiter | None = None


def _hash_limiter() -> anyio.CapacityLimiter:
    # Создаётся лениво: CapacityLimiter привязан к работающему event loop
    global _limiter
    if _limiter is None:
        _limiter = anyio.CapacityLimiter(MAX_CONCURRENT_HASHES)
    return _limiter


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


async def hash_password_async(password: str) -> str:
    return await anyio.to_thread.run_sync(hash_password, password, limiter=_hash_limiter())


async def verify_password_async(password: str, password_hash: str | None) -> bool:
    return await anyio.to_thread.run_sync(
        verify_password, password, password_hash, limiter=_hash_limiter()
    )


def new_token() -> str:
    """Непрозрачный случайный токен (сессии, одноразовые коды)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sign(message: str, secret: str) -> str:
    """HMAC-SHA256 подпись (подписанные ссылки на файлы)."""
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_signature(message: str, signature: str, secret: str) -> bool:
    return hmac.compare_digest(sign(message, secret), signature)

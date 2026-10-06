import hashlib
import hmac
import secrets

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()  # argon2id

# Проверяется, когда пользователь не найден: время ответа не выдаёт, есть ли такой email.
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


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

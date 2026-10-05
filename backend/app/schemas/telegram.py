from datetime import datetime

from pydantic import BaseModel


class TelegramStatus(BaseModel):
    linked: bool
    bot_username: str | None


class TelegramLinkCodeRead(BaseModel):
    code: str
    expires_at: datetime
    deep_link: str | None

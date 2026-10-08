"""Провайдер для тестов: отвечает заготовленными текстами по очереди."""

from collections.abc import Callable, Sequence
from typing import Any

from app.ai.provider import ChatProvider, Message, RawReply

Reply = str | Callable[[Sequence[Message]], str] | Exception


class FakeProvider(ChatProvider):
    name = "fake"

    def __init__(self, replies: Sequence[Reply] = ()) -> None:
        super().__init__("fake-text", "fake-vision")
        self.replies: list[Reply] = list(replies)
        # Что приходило в каждый вызов: (сообщения, модель)
        self.calls: list[tuple[list[Message], str]] = []

    def push(self, *replies: Reply) -> None:
        self.replies.extend(replies)

    async def _chat(
        self, messages: Sequence[Message], json_schema: dict[str, Any], model: str, name: str
    ) -> RawReply:
        self.calls.append((list(messages), model))
        if not self.replies:
            raise AssertionError("FakeProvider: ответы кончились")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        text = reply(messages) if callable(reply) else reply
        return RawReply(text=text, model=model, prompt_tokens=10, completion_tokens=20)

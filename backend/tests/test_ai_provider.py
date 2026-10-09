"""M10.1: провайдеры ИИ — JSON по схеме, валидация, один повтор, HTTP-форматы."""

import json
from datetime import date, time

import httpx
import pytest
from pydantic import BaseModel

from app.ai import Image, LLMInvalidError, LLMUnavailableError, Message
from app.ai.fake import FakeProvider
from app.ai.provider import OllamaProvider, OpenAICompatProvider, extract_json
from app.ai.schemas import AIBreakdown, AIParsed, with_subjects
from app.core.config import settings


class Answer(BaseModel):
    value: int


MSGS = [Message("system", "ты помощник"), Message("user", "скажи число")]


def test_extract_json_tolerates_think_fences_and_chatter():
    assert extract_json('{"value": 1}') == {"value": 1}
    assert extract_json('<think>хм</think>\n```json\n{"value": 2}\n```') == {"value": 2}
    assert extract_json('Вот ответ: {"value": 3}. Удачи!') == {"value": 3}
    with pytest.raises(ValueError, match="Expecting value"):
        extract_json("нет json")


async def test_valid_first_time():
    fake = FakeProvider(['{"value": 7}'])
    result = await fake.complete_json(MSGS, Answer)
    assert result.value.value == 7
    assert [a.ok for a in result.attempts] == [True]
    assert result.attempts[0].prompt_tokens == 10


async def test_one_retry_with_error_text():
    fake = FakeProvider(['{"value": "семь"}', '{"value": 7}'])
    result = await fake.complete_json(MSGS, Answer)
    assert result.value.value == 7
    assert [a.ok for a in result.attempts] == [False, True]
    retry_msgs, _ = fake.calls[1]
    assert retry_msgs[-2].role == "assistant"
    assert "value" in retry_msgs[-1].content
    assert "не прошёл проверку" in retry_msgs[-1].content


async def test_two_invalid_answers_fail():
    fake = FakeProvider(["мусор", '{"nope": 1}'])
    with pytest.raises(LLMInvalidError) as exc:
        await fake.complete_json(MSGS, Answer)
    assert len(exc.value.attempts) == 2
    assert not any(a.ok for a in exc.value.attempts)


async def test_network_error_is_unavailable_without_retry():
    fake = FakeProvider([httpx.ConnectError("нет связи"), '{"value": 1}'])
    with pytest.raises(LLMUnavailableError) as exc:
        await fake.complete_json(MSGS, Answer)
    assert len(fake.calls) == 1
    assert "ConnectError" in exc.value.attempts[0].error


async def test_images_go_to_vision_model_and_last_user_message():
    fake = FakeProvider(['{"value": 1}'])
    result = await fake.complete_json(MSGS, Answer, images=[Image(b"jpg")])
    msgs, model = fake.calls[0]
    assert model == "fake-vision"
    assert msgs[-1].images
    assert not msgs[0].images
    assert result.attempts[0].request[-1]["images"] == 1


# ---------- схемы ----------


def breakdown(**over):
    data = {
        "task_type": "essay",
        "category": "study",
        "subtasks": [
            {
                "order": 1,
                "title": "Найти источники",
                "estimate_min": 10,
                "action_type": "study",
                "depends_on": [],
                "note": "",
            },
            {
                "order": 2,
                "title": "  Написать   текст ",
                "estimate_min": 200,
                "action_type": "study",
                "depends_on": [1],
                "note": "",
            },
        ],
        "total_estimate_min": 210,
        "warning": "  ",
    }
    data.update(over)
    return data


def test_breakdown_schema_fixes_small_things():
    b = AIBreakdown.model_validate(breakdown())
    assert [s.estimate_min for s in b.subtasks] == [15, 120]
    assert b.subtasks[1].title == "Написать текст"
    assert b.warning is None


@pytest.mark.parametrize(
    ("deps", "error"),
    [([2], "сам от себя"), ([5], "несуществующие"), ([], None)],
)
def test_breakdown_schema_rejects_broken_deps(deps, error):
    data = breakdown()
    data["subtasks"][1]["depends_on"] = deps
    if error is None:
        AIBreakdown.model_validate(data)
        return
    with pytest.raises(ValueError, match=error):
        AIBreakdown.model_validate(data)


def test_breakdown_schema_rejects_cycle():
    data = breakdown()
    data["subtasks"][0]["depends_on"] = [2]
    with pytest.raises(ValueError, match="цикл"):
        AIBreakdown.model_validate(data)


def test_schema_for_model_has_no_string_lengths():
    from app.ai.provider import model_schema

    text = json.dumps(model_schema(AIParsed))
    for key in ("maxLength", "minLength", "$ref", "$defs", '"format"'):
        assert key not in text
    # Перечисление — без null: «нет» — это other
    assert "homework" in model_schema(AIParsed)["properties"]["task_type"]["enum"]
    assert "maxItems" in json.dumps(model_schema(AIBreakdown))
    assert "title" in model_schema(AIParsed)["properties"]
    assert "title" in model_schema(AIBreakdown)["properties"]["subtasks"]["items"]["properties"]


def parsed(**over):
    data = {
        "kind": "task",
        "title": "x",
        "task_type": "other",
        "subject": "",
        "deadline_date": "",
        "deadline_time": "",
        "action_type": "study",
        "description": "",
    }
    return {**data, **over}


def test_subject_enum_in_schema():
    from app.ai.provider import model_schema

    schema = with_subjects(AIParsed, ["Климатология", "Физика атмосферы"])
    subject = model_schema(schema)["properties"]["subject"]
    assert subject["enum"] == ["Климатология", "Физика атмосферы", ""]
    assert schema.model_validate(parsed(subject="Климатология")).subject == "Климатология"
    assert schema.model_validate(parsed(subject="")).subject is None
    with pytest.raises(ValueError, match="предмет не из списка"):
        schema.model_validate(parsed(subject="История"))
    assert with_subjects(AIParsed, []) is AIParsed
    # Порядок полей — как в модели: kind первым
    assert next(iter(schema.model_fields)) == "kind"


def test_parsed_empty_strings_and_time():
    p = AIParsed.model_validate(parsed(deadline_date="2026-10-15", deadline_time="9:30"))
    assert p.deadline_wall() == (date(2026, 10, 15), time(9, 30))
    empty = AIParsed.model_validate(parsed(deadline_time="null"))
    assert empty.deadline_date is None
    assert empty.deadline_time is None
    assert empty.deadline_wall() is None
    with pytest.raises(ValueError, match="ЧЧ:ММ"):
        AIParsed.model_validate(parsed(deadline_time="25:00"))
    with pytest.raises(ValueError, match="пустое название"):
        AIParsed.model_validate(parsed(title="  "))


# ---------- HTTP ----------


async def test_ollama_request_and_reply():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((request.url.path, body))
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "message": {"role": "assistant", "content": '{"value": 5}'},
                "prompt_eval_count": 11,
                "eval_count": 3,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider("http://ollama:11434/", "qwen3:8b", "qwen2.5vl:7b", client=client)
    result = await provider.complete_json(MSGS, Answer, images=[Image(b"\x00")])
    path, body = seen[0]
    assert path == "/api/chat"
    assert body["model"] == "qwen2.5vl:7b"
    assert body["format"]["properties"]["value"]["type"] == "integer"
    assert body["stream"] is False
    assert body["think"] is False
    assert body["messages"][-1]["images"] == ["AA=="]
    assert result.value.value == 5
    assert (result.attempts[0].prompt_tokens, result.attempts[0].completion_tokens) == (11, 3)


async def test_ollama_model_without_think_support():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "think" in body:
            return httpx.Response(400, json={"error": "model does not support thinking"})
        return httpx.Response(200, json={"message": {"content": '{"value": 1}'}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OllamaProvider("http://o", "qwen2.5:7b-instruct", client=client)
    assert (await provider.complete_json(MSGS, Answer)).value.value == 1
    assert len(bodies) == 2


async def test_ollama_http_error_is_unavailable():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    provider = OllamaProvider("http://o", "m", client=client)
    with pytest.raises(LLMUnavailableError):
        await provider.complete_json(MSGS, Answer)


async def test_openai_compat_request_and_reply():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": "gpt-x",
                "choices": [{"message": {"content": '{"value": 9}'}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatProvider("https://api.example/v1", "sk-1", "gpt-x", client=client)
    result = await provider.complete_json(MSGS, Answer, images=[Image(b"\x00", "image/png")])
    request = seen[0]
    body = json.loads(request.content)
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-1"
    assert body["response_format"]["json_schema"]["name"] == "Answer"
    content = body["messages"][-1]["content"]
    assert content[1]["image_url"]["url"] == "data:image/png;base64,AA=="
    assert result.value.value == 9
    assert result.attempts[0].prompt_tokens == 4


# ---------- запасной провайдер ----------


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_fallback_when_primary_unavailable_and_cooldown():
    from app.ai.provider import FallbackProvider

    primary = FakeProvider([httpx.ConnectError("мак спит")])
    backup = FakeProvider(['{"value": 1}', '{"value": 2}', '{"value": 3}'])
    clock = Clock()
    provider = FallbackProvider(primary, backup, cooldown_sec=300, clock=clock)

    first = await provider.complete_json(MSGS, Answer)
    assert first.value.value == 1
    assert [a.ok for a in first.attempts] == [False, True]  # обе попытки — в ai_log

    # В течение паузы основной не трогаем вовсе
    clock.now = 100
    assert (await provider.complete_json(MSGS, Answer)).value.value == 2
    assert len(primary.calls) == 1

    # Пауза прошла — снова основной
    clock.now = 301
    primary.push('{"value": 9}')
    assert (await provider.complete_json(MSGS, Answer)).value.value == 9
    assert len(backup.calls) == 2


async def test_fallback_after_invalid_answer_without_cooldown():
    from app.ai.provider import FallbackProvider

    primary = FakeProvider(["мусор", "мусор", '{"value": 5}'])
    backup = FakeProvider(['{"value": 7}'])
    provider = FallbackProvider(primary, backup, clock=Clock())
    assert (await provider.complete_json(MSGS, Answer)).value.value == 7
    # Ответ не по схеме — не повод считать основной недоступным
    assert (await provider.complete_json(MSGS, Answer)).value.value == 5


async def test_fallback_both_fail():
    from app.ai.provider import FallbackProvider

    primary = FakeProvider([httpx.ConnectError("нет")])
    backup = FakeProvider([httpx.ConnectError("и тут нет")])
    provider = FallbackProvider(primary, backup, clock=Clock())
    with pytest.raises(LLMUnavailableError) as exc:
        await provider.complete_json(MSGS, Answer)
    assert len(exc.value.attempts) == 2


async def test_openai_compat_downgrades_to_json_object():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": "response_format json_schema unsupported"})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"value": 4}'}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatProvider(
        "https://api.timeweb.ai/v1", "k", "openai/gpt-4o", client=client
    )
    assert (await provider.complete_json(MSGS, Answer)).value.value == 4
    # Схема ушла текстом в системное сообщение, и дальше сразу json_object
    assert '"value"' in bodies[1]["messages"][0]["content"]
    assert (await provider.complete_json(MSGS, Answer)).value.value == 4
    assert [b["response_format"]["type"] for b in bodies] == [
        "json_schema",
        "json_object",
        "json_object",
    ]


def test_build_provider_with_fallback(monkeypatch):
    from pydantic import SecretStr

    from app.ai import build_provider
    from app.ai.provider import FallbackProvider

    monkeypatch.setattr(settings, "LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_FALLBACK_BASE_URL", "https://api.timeweb.ai/v1")
    monkeypatch.setattr(settings, "LLM_FALLBACK_API_KEY", SecretStr("k"))
    monkeypatch.setattr(settings, "LLM_FALLBACK_MODEL", "openai/gpt-4o")
    provider = build_provider()
    assert isinstance(provider, FallbackProvider)
    assert isinstance(provider.primary, OllamaProvider)
    assert isinstance(provider.fallback, OpenAICompatProvider)
    assert provider.fallback.vision_model == "openai/gpt-4o"
    assert provider.primary.timeout.connect == settings.LLM_CONNECT_TIMEOUT_SEC


def test_ai_queue_backoff():
    from app.services.jobs import JobOutcome
    from app.worker.__main__ import AI_POLL_SEC, ai_pause

    assert ai_pause(None, 3) == (AI_POLL_SEC, 3)
    assert ai_pause(JobOutcome.deferred, 0) == (30, 1)
    assert ai_pause(JobOutcome.deferred, 1) == (60, 2)
    assert ai_pause(JobOutcome.deferred, 9) == (300, 10)
    # ИИ ответил — дальше без пауз, очередь разбирается подряд
    assert ai_pause(JobOutcome.done, 9) == (0.0, 0)
    assert ai_pause(JobOutcome.failed, 2) == (0.0, 0)


# ---------- L-04: постоянные ошибки API не ждут в очереди ----------


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
async def test_client_errors_are_rejected_not_unavailable(code: int):
    from app.ai.provider import LLMRejectedError

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(code)))
    provider = OpenAICompatProvider("http://o/v1", "key", "m", client=client)
    provider.json_object = True  # без повтора с json_object на 400
    with pytest.raises(LLMRejectedError):
        await provider.complete_json(MSGS, Answer)


@pytest.mark.parametrize("code", [408, 429, 500, 502, 503])
async def test_transient_errors_stay_unavailable(code: int):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(code)))
    provider = OllamaProvider("http://o", "m", client=client)
    with pytest.raises(LLMUnavailableError):
        await provider.complete_json(MSGS, Answer)


@pytest.mark.parametrize("body", [{"choices": []}, {"choices": [None]}, {"choices": "x"}])
async def test_malformed_envelope_is_unavailable(body: dict):
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    )
    provider = OpenAICompatProvider("http://o/v1", None, "m", client=client)
    with pytest.raises(LLMUnavailableError):
        await provider.complete_json(MSGS, Answer)


async def test_fallback_after_rejected_primary_without_cooldown():
    from app.ai.provider import FallbackProvider, LLMRejectedError

    primary = FakeProvider([LLMRejectedError(), '{"value": 5}'])
    backup = FakeProvider(['{"value": 7}'])
    provider = FallbackProvider(primary, backup, clock=Clock())
    assert (await provider.complete_json(MSGS, Answer)).value.value == 7
    assert (await provider.complete_json(MSGS, Answer)).value.value == 5


async def test_rejected_request_fails_job_at_once(session, user):
    from app.ai import set_provider
    from app.ai.provider import LLMRejectedError
    from app.domain.enums import AIPurpose
    from app.services.ai import call_llm
    from app.services.jobs import JobFailedError

    set_provider(FakeProvider([LLMRejectedError()]))
    try:
        with pytest.raises(JobFailedError):
            await call_llm(session, user.id, AIPurpose.parse, MSGS, Answer)
    finally:
        set_provider(None)

"""L-14: все ошибки API — в одном формате {"error": {"code", "message"}}."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import register_exception_handlers
from app.main import app

API = "/api/v1"


def assert_error(resp, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]
    return body["error"]


async def test_validation_error_format(client: AsyncClient):
    err = assert_error(await client.post(f"{API}/auth/login", json={}), 422, "validation_error")
    assert "email" in err["message"]
    assert "body" not in err["message"]


async def test_unknown_route_and_method(client: AsyncClient):
    assert_error(await client.get(f"{API}/nope"), 404, "not_found")
    assert_error(await client.delete(f"{API}/health"), 405, "method_not_allowed")


async def test_unhandled_error_is_generic_500():
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("секретная деталь")

    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/boom")
    err = assert_error(resp, 500, "internal_error")
    assert "секретная" not in err["message"]


def test_openapi_documents_error_format():
    spec = app.openapi()
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    responses = spec["paths"][f"{API}/tasks"]["post"]["responses"]
    for code in ("401", "413", "422", "429"):
        assert responses[code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }

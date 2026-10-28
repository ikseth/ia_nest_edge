from __future__ import annotations

import asyncio
import json
import threading
import time

import httpx
import pytest

from ianest_edge.client import ForwardedJson
from ianest_edge.identity import DirectoryIdentityResolver, LdapDirectoryClient
from ianest_edge.rest import create_app
from ianest_edge.service import EdgeService

from .conftest import BEARER, KEY


def _requests(app, actions):
    async def run():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return [await action(client) for action in actions]

    return asyncio.run(run())


def _headers(person="adult@test"):
    return {"Authorization": BEARER, "X-Person": person}


def _api_headers():
    return {"Authorization": f"Bearer api_service.{KEY}"}


def _audit(config):
    return [
        json.loads(line)
        for line in config.audit_path.read_text(encoding="ascii").splitlines()
    ]


def test_unauthorized_request_never_calls_extended(service, extended):
    app = create_app(service.config, service)

    async def request(client):
        extended.calls.clear()
        return await client.post("/v1/chat/completions", content=b"not-json")

    response = _requests(app, [request])[0]
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert extended.calls == []


def test_openai_models_and_completion(service):
    app = create_app(service.config, service)

    async def models(client):
        return await client.get("/v1/models", headers=_headers())

    async def completion(client):
        return await client.post(
            "/v1/chat/completions",
            headers=_headers(),
            json={
                "model": "direct",
                "messages": [{"role": "user", "content": "hola"}],
            },
        )

    responses = _requests(app, [models, completion])
    assert [response.status_code for response in responses] == [200, 200]


def test_non_asserting_account_identity_reaches_openai_and_rest(service, extended):
    app = create_app(service.config, service)

    async def openai(client):
        return await client.post(
            "/v1/chat/completions",
            headers=_api_headers(),
            json={
                "model": "direct",
                "messages": [{"role": "user", "content": "hola"}],
            },
        )

    async def rest(client):
        return await client.post(
            "/rest/prompt/run",
            headers=_api_headers(),
            json={"prompt": "hola"},
        )

    responses = _requests(app, [openai, rest])
    assert [item.status_code for item in responses] == [200, 200]
    openai_call = next(item for item in extended.calls if item[0] == "prompt.run")
    rest_call = next(item for item in extended.calls if item[0] == "forward")
    for identity in (openai_call[1]["identity"], rest_call[4]["identity"]):
        assert identity["user_id"] == "api_service"
        assert identity["service"] == "api"


def test_rest_forwards_method_query_and_overrides_identity(
    service, extended, config
):
    app = create_app(service.config, service)

    async def request(client):
        return await client.post(
            "/rest/prompt/run?dry=true",
            headers=_headers(),
            json={"prompt": "hola", "identity": {"user_id": "attacker"}},
        )

    response = _requests(app, [request])[0]
    assert response.status_code == 200
    call = next(item for item in extended.calls if item[0] == "forward")
    assert call[1:4] == ("POST", "/prompt/run", "dry=true")
    assert call[4]["identity"] == {
        "user_id": "adult_user",
        "service": "open_webui",
        "interlocutor_profile": "adult",
    }
    record = _audit(config)[-1]
    assert record["identity_overridden"] is True
    assert record["face"] == "rest"


@pytest.mark.parametrize(
    ("method", "content", "headers", "status"),
    [
        ("GET", None, {}, 200),
        ("POST", b'{"prompt":"hola"}', {"Content-Type": "text/plain"}, 200),
        ("POST", b"[]", {"Content-Type": "application/json"}, 400),
        ("POST", b"no es json", {"Content-Type": "text/plain"}, 400),
    ],
)
def test_rest_always_forwards_edge_identity_in_json(
    service, extended, method, content, headers, status
):
    app = create_app(service.config, service)

    async def request(client):
        return await client.request(
            method,
            "/rest/prompt/run",
            headers={**_headers(), **headers},
            content=content,
        )

    extended.calls.clear()
    response = _requests(app, [request])[0]
    assert response.status_code == status
    forwards = [call for call in extended.calls if call[0] == "forward"]
    if status == 200:
        assert forwards[0][4]["identity"] == {
            "user_id": "adult_user",
            "service": "open_webui",
            "interlocutor_profile": "adult",
        }
    else:
        assert forwards == []


def test_rest_disallowed_capability_is_403_without_extended_call(
    service, extended, config
):
    app = create_app(service.config, service)

    async def request(client):
        extended.calls.clear()
        return await client.post(
            "/rest/not/allowed", headers=_headers(), json={}
        )

    response = _requests(app, [request])[0]
    assert response.status_code == 403
    assert extended.calls == []
    assert _audit(config)[-1]["outcome"] == "capability_not_allowed"


def test_missing_asserted_person_is_403_and_audited(service, extended, config):
    app = create_app(service.config, service)

    async def request(client):
        extended.calls.clear()
        return await client.get(
            "/v1/models", headers={"Authorization": BEARER}
        )

    response = _requests(app, [request])[0]
    assert response.status_code == 403
    assert extended.calls == []
    assert _audit(config)[-1]["outcome"] == "forbidden"


def test_new_catalog_capability_needs_only_configuration(
    tmp_path, directory, extended
):
    from ianest_edge.audit import AuditWriter
    from ianest_edge.config import EdgeConfig
    from ianest_edge.identity import DirectoryIdentityResolver
    from ianest_edge.service import EdgeService
    from .conftest import _capability, config_dict

    raw = config_dict(tmp_path)
    raw["api"]["allowed_capabilities"].append("future.echo")
    config = EdgeConfig.from_dict(raw)
    extended.capabilities.append(_capability("future.echo"))
    edge = EdgeService(
        config,
        resolver=DirectoryIdentityResolver(config, directory),
        client=extended,
        audit=AuditWriter(config.audit_path),
    )
    app = create_app(config, edge)

    async def request(client):
        return await client.post(
            "/rest/future/echo", headers=_headers(), json={"value": 1}
        )

    assert _requests(app, [request])[0].status_code == 200


def test_rest_stream_arrives_as_separate_events(service):
    app = create_app(service.config, service)

    async def request(client):
        return await client.post(
            "/rest/prompt/stream", headers=_headers(), json={"prompt": "hola"}
        )

    response = _requests(app, [request])[0]
    assert response.status_code == 200
    assert response.text == "event: token\ndata: one\n\nevent: done\ndata: {}\n\n"


def test_downstream_json_error_keeps_status_and_fields(service, extended):
    expected = {
        "error": {
            "type": "CoreSpecificError",
            "message": "fallo",
            "origin": "ia_nest_core",
            "request_id": "core-7",
        }
    }
    extended.forward = lambda *args, **kwargs: ForwardedJson(
        expected, 409, "application/json"
    )
    app = create_app(service.config, service)

    async def request(client):
        return await client.post(
            "/rest/prompt/run", headers=_headers(), json={"prompt": "hola"}
        )

    response = _requests(app, [request])[0]
    assert response.status_code == 409
    assert response.json() == expected


def test_blocking_downstream_does_not_block_another_request(service, extended):
    app = create_app(service.config, service)
    started = threading.Event()
    original_run = extended.run

    def slow_run(capability, payload):
        started.set()
        time.sleep(0.2)
        return original_run(capability, payload)

    extended.run = slow_run

    async def run():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                first = asyncio.create_task(
                    client.post(
                        "/v1/chat/completions",
                        headers=_headers(),
                        json={
                            "model": "direct",
                            "messages": [{"role": "user", "content": "lenta"}],
                        },
                    )
                )
                while not started.is_set():
                    await asyncio.sleep(0.001)
                before = time.monotonic()
                models = await client.get("/v1/models", headers=_headers())
                elapsed = time.monotonic() - before
                await first
                return models, elapsed

    models, elapsed = asyncio.run(run())
    assert models.status_code == 200
    assert elapsed < 0.15


@pytest.mark.parametrize(
    ("path", "face"),
    [("/v1/models", "openai"), ("/rest/prompt/run", "rest"), ("/mcp", "mcp")],
)
def test_directory_down_is_503_for_all_faces(
    service, directory, config, path, face
):
    directory.unavailable = True
    app = create_app(service.config, service)

    async def request(client):
        if path == "/v1/models":
            return await client.get(path, headers=_headers())
        return await client.post(path, headers=_headers(), json={})

    response = _requests(app, [request])[0]
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "DirectoryUnavailableError"
    record = _audit(config)[-1]
    assert record["face"] == face
    assert record["outcome"] == "directory_unavailable"


def test_arbitrary_ldap_bind_error_is_503_and_audited(
    config, extended, monkeypatch
):
    import ldap3

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def bind(self):
            raise ValueError("bind inesperado")

    monkeypatch.setattr(ldap3, "Server", lambda *args, **kwargs: object())
    monkeypatch.setattr(ldap3, "Connection", Connection)
    resolver = DirectoryIdentityResolver(
        config, LdapDirectoryClient(config.directory)
    )
    service = EdgeService(config, resolver=resolver, client=extended)
    app = create_app(service.config, service)

    async def request(client):
        return await client.get("/v1/models", headers=_headers())

    response = _requests(app, [request])[0]
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "DirectoryUnavailableError"
    assert _audit(config)[-1]["outcome"] == "directory_unavailable"

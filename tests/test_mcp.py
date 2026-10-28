from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from ianest_edge.client import ForwardedJson
from ianest_edge.rest import create_app

from .conftest import BEARER, KEY


def _mcp_requests(app, payloads, *, authorization=BEARER, person="adult@test"):
    async def run():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8080"
            ) as client:
                headers = {
                    "Authorization": authorization,
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": "2025-03-26",
                }
                if person is not None:
                    headers["X-Person"] = person
                return [
                    await client.post("/mcp", headers=headers, json=payload)
                    for payload in payloads
                ]

    return asyncio.run(run())


def _request(request_id, method, params):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }


def _audit(config):
    return [
        json.loads(line)
        for line in config.audit_path.read_text(encoding="ascii").splitlines()
    ]


def test_tools_list_comes_from_catalog_and_filters_allowed_and_streaming(
    service, extended
):
    app = create_app(service.config, service)
    response = _mcp_requests(app, [_request(1, "tools/list", {})])[0]
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["result"]["tools"]]
    assert names == [
        "capability.list",
        "prompt.run",
        "runtime.health",
        "session.list",
    ]
    assert "prompt.stream" not in names
    assert "not.allowed" not in names
    assert any(call[0] == "capability.list" for call in extended.calls)


def test_mcp_requires_bearer_before_protocol(service, extended):
    app = create_app(service.config, service)

    async def run():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8080"
            ) as client:
                return await client.post(
                    "/mcp", json=_request(99, "tools/list", {})
                )

    response = asyncio.run(run())
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert not any(call[0] == "capability.list" for call in extended.calls)


@pytest.mark.parametrize("path", ["/mcp/", "/anything"])
def test_all_mcp_mount_paths_require_authentication(service, directory, path):
    app = create_app(service.config, service)

    async def run():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8080"
            ) as client:
                unauthenticated = await client.post(
                    path, json=_request(99, "tools/list", {})
                )
                directory.unavailable = True
                unavailable = await client.post(
                    path,
                    headers={"Authorization": BEARER},
                    json=_request(99, "tools/list", {}),
                )
                return unauthenticated, unavailable

    response, unavailable = asyncio.run(run())
    assert response.status_code in {401, 404}
    assert unavailable.status_code == 503


def test_tools_call_uses_rest_projection_and_forwards_session(
    service, extended, config
):
    app = create_app(service.config, service)
    response = _mcp_requests(
        app,
        [
            _request(
                2,
                "tools/call",
                {
                    "name": "prompt.run",
                    "arguments": {
                        "prompt": "hola",
                        "identity": {"user_id": "attacker", "session_id": "s1"},
                    },
                },
            )
        ],
    )[0]
    result = response.json()["result"]
    assert result.get("isError", False) is False
    call = next(item for item in extended.calls if item[0] == "forward")
    assert call[1:3] == ("POST", "/prompt/run")
    assert call[4]["identity"] == {
        "user_id": "adult_user",
        "service": "open_webui",
        "interlocutor_profile": "adult",
        "session_id": "s1",
    }
    record = _audit(config)[-1]
    assert record["face"] == "mcp"
    assert record["identity_overridden"] is True


def test_tools_call_without_arguments_forwards_edge_identity(service, extended):
    app = create_app(service.config, service)
    response = _mcp_requests(
        app, [_request(22, "tools/call", {"name": "prompt.run"})]
    )[0]
    assert response.status_code == 200
    call = next(item for item in extended.calls if item[0] == "forward")
    assert call[4]["identity"]["user_id"] == "adult_user"


def test_non_asserting_account_identity_reaches_mcp(service, extended):
    app = create_app(service.config, service)
    response = _mcp_requests(
        app,
        [
            _request(
                20,
                "tools/call",
                {"name": "prompt.run", "arguments": {"prompt": "hola"}},
            )
        ],
        authorization=f"Bearer api_service.{KEY}",
        person=None,
    )[0]
    assert response.status_code == 200
    call = next(item for item in extended.calls if item[0] == "forward")
    assert call[4]["identity"]["user_id"] == "api_service"
    assert call[4]["identity"]["service"] == "api"


def test_disallowed_tool_call_is_typed_error_without_forward(service, extended):
    app = create_app(service.config, service)
    extended.calls.clear()
    response = _mcp_requests(
        app,
        [
            _request(
                3,
                "tools/call",
                {"name": "not.allowed", "arguments": {}},
            )
        ],
    )[0]
    result = response.json()["result"]
    assert result["isError"] is True
    error = json.loads(result["content"][0]["text"])["error"]
    assert error["type"] == "CapabilityNotAllowedError"
    assert not any(call[0] == "forward" for call in extended.calls)


def test_downstream_error_is_mcp_error_result_without_retyping(service, extended):
    expected = {
        "error": {
            "type": "CoreSpecificError",
            "message": "fallo",
            "origin": "ia_nest_core",
        }
    }
    extended.forward = lambda *args, **kwargs: ForwardedJson(
        expected, 409, "application/json"
    )
    app = create_app(service.config, service)
    response = _mcp_requests(
        app,
        [
            _request(
                30,
                "tools/call",
                {"name": "prompt.run", "arguments": {"prompt": "hola"}},
            )
        ],
    )[0]
    result = response.json()["result"]
    assert result["isError"] is True
    assert json.loads(result["content"][0]["text"]) == expected


def test_future_capability_appears_without_edge_code_change(
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
    listed, called = _mcp_requests(
        app,
        [
            _request(4, "tools/list", {}),
            _request(
                5,
                "tools/call",
                {"name": "future.echo", "arguments": {"value": 1}},
            ),
        ],
    )
    names = [item["name"] for item in listed.json()["result"]["tools"]]
    assert "future.echo" in names
    assert called.json()["result"].get("isError", False) is False

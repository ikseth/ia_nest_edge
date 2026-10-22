from __future__ import annotations

import asyncio
import threading
import time

import pytest

pytest.importorskip("starlette")
pytest.importorskip("httpx")

import httpx

from ianest_edge.rest import create_app

from .conftest import KEY


def _requests(app, actions):
    async def run():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return [await action(client) for action in actions]

    return asyncio.run(run())


def test_unauthorized_request_never_calls_extended(service, extended):
    app = create_app(service.config, service)

    async def request(client):
        extended.calls.clear()
        return await client.post("/v1/chat/completions", content=b"not-json")

    response = _requests(app, [request])[0]

    assert response.status_code == 401
    assert response.json()["error"]["origin"] == "ia_nest_edge"
    assert extended.calls == []


def test_models_and_completion_endpoints(service):
    app = create_app(service.config, service)
    headers = {"Authorization": f"Bearer {KEY}", "X-Person": "adult"}

    async def models_request(client):
        return await client.get("/v1/models", headers=headers)

    async def completion_request(client):
        return await client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "direct",
                "messages": [{"role": "user", "content": "hola"}],
            },
        )

    models, completion = _requests(
        app, [models_request, completion_request]
    )

    assert models.status_code == 200
    assert completion.status_code == 200
    assert completion.json()["object"] == "chat.completion"


def test_streaming_endpoint_ends_with_done(service):
    app = create_app(service.config, service)
    headers = {"Authorization": f"Bearer {KEY}", "X-Person": "adult"}

    async def request(client):
        return await client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "direct",
                "stream": True,
                "messages": [{"role": "user", "content": "hola"}],
            },
        )

    response = _requests(app, [request])[0]

    assert response.status_code == 200
    assert response.text.endswith("data: [DONE]\n\n")


def test_slow_extended_request_does_not_block_another_request(service, extended):
    app = create_app(service.config, service)
    headers = {"Authorization": f"Bearer {KEY}", "X-Person": "adult"}
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
                first = asyncio.create_task(client.post(
                    "/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": "direct",
                        "messages": [{"role": "user", "content": "lenta"}],
                    },
                ))
                while not started.is_set():
                    await asyncio.sleep(0.001)
                before = time.monotonic()
                models = await client.get("/v1/models", headers=headers)
                elapsed = time.monotonic() - before
                await first
                return models, elapsed

    models, elapsed = asyncio.run(run())

    assert models.status_code == 200
    assert elapsed < 0.15

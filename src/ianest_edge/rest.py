"""Piel HTTP compatible con los endpoints OpenAI de conversacion."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager

from .config import EdgeConfig
from .errors import (
    AuthenticationError,
    DownstreamError,
    EdgeError,
    RequestValidationError,
)
from .service import CompletionResult, EdgeService, StreamingResult


def create_app(
    config: EdgeConfig | None = None,
    service: EdgeService | None = None,
):
    try:
        from starlette.applications import Starlette
        from starlette.background import BackgroundTask
        from starlette.concurrency import run_in_threadpool
        from starlette.requests import Request
        from starlette.responses import JSONResponse, StreamingResponse
        from starlette.routing import Route
    except ImportError as exc:  # pragma: no cover - depende de la instalacion
        raise RuntimeError(
            "dependencias REST no instaladas; instala ianest-edge"
        ) from exc

    active_config = config or EdgeConfig.from_env()
    if service is None:
        raise TypeError("create_app requiere un EdgeService construido con resolver")
    active_service = service

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(active_service.validate_startup)
        yield

    async def models(request: Request):
        started = time.monotonic()
        identity = await _authenticate(active_service, request, started)
        payload = await run_in_threadpool(active_service.models, identity, started)
        return JSONResponse(payload)

    async def chat_completions(request: Request):
        started = time.monotonic()
        identity = await _authenticate(active_service, request, started)
        try:
            raw = await request.body()
            try:
                body = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                active_service.audit_resolved_failure(identity, started)
                raise RequestValidationError(
                    "el cuerpo no contiene JSON valido", "body"
                ) from exc
            result = await run_in_threadpool(
                active_service.chat, identity, request.headers, body, started
            )
        except (EdgeError, DownstreamError):
            raise
        if isinstance(result, CompletionResult):
            return JSONResponse(result.payload)
        assert isinstance(result, StreamingResult)
        return StreamingResponse(
            result.body,
            media_type="text/event-stream",
            background=BackgroundTask(_close_stream, result.body),
        )

    async def edge_error_handler(request: Request, exc: EdgeError):
        headers = None
        if isinstance(exc, AuthenticationError):
            headers = {"WWW-Authenticate": "Bearer"}
        return JSONResponse(
            {"error": exc.to_dict()},
            status_code=exc.status_code,
            headers=headers,
        )

    async def downstream_error_handler(request: Request, exc: DownstreamError):
        return JSONResponse(
            {"error": exc.error},
            status_code=exc.status_code,
        )

    return Starlette(
        routes=[
            Route("/v1/models", models, methods=["GET"]),
            Route(
                "/v1/chat/completions",
                chat_completions,
                methods=["POST"],
            ),
        ],
        exception_handlers={
            EdgeError: edge_error_handler,
            DownstreamError: downstream_error_handler,
        },
        lifespan=lifespan,
    )


async def _authenticate(service: EdgeService, request, started: float):
    from starlette.concurrency import run_in_threadpool

    try:
        return await run_in_threadpool(
            service.authenticate_and_resolve,
            request.headers.get("authorization"),
            request.headers,
        )
    except AuthenticationError:
        await run_in_threadpool(service.audit_authentication_failure, started)
        raise


def _close_stream(body) -> None:
    """Cierra el generador tambien cuando el cliente corta la respuesta."""
    close = getattr(body, "close", None)
    if close is not None:
        close()

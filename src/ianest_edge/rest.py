"""Caras HTTP OpenAI, REST uniforme y MCP del borde."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager

from .async_utils import run_sync
from .client import ForwardedJson, ForwardedStream
from .config import EdgeConfig
from .errors import (
    AuthenticationError,
    AuthorizationError,
    DirectoryUnavailableError,
    DownstreamError,
    EdgeError,
    RequestValidationError,
)
from .mcp_server import create_mcp_app
from .service import CompletionResult, EdgeService, StreamingResult


def create_app(
    config: EdgeConfig | None = None,
    service: EdgeService | None = None,
):
    try:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse, StreamingResponse
        from starlette.routing import Mount, Route
    except ImportError as exc:  # pragma: no cover - depende de la instalacion
        raise RuntimeError(
            "dependencias REST no instaladas; instala ianest-edge"
        ) from exc

    if service is None:
        raise TypeError("create_app requiere un EdgeService construido con resolver")
    active_service = service
    mcp_app = create_mcp_app(active_service)

    @asynccontextmanager
    async def lifespan(app):
        await run_sync(active_service.validate_startup)
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    async def models(request: Request):
        started = time.monotonic()
        identity = await _authenticate(active_service, request, started, "openai")
        payload = await run_sync(active_service.models, identity, started)
        return JSONResponse(payload)

    async def chat_completions(request: Request):
        started = time.monotonic()
        identity = await _authenticate(active_service, request, started, "openai")
        try:
            raw = await request.body()
            try:
                body = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                active_service.audit_resolved_failure(identity, started)
                raise RequestValidationError(
                    "el cuerpo no contiene JSON valido", "body"
                ) from exc
            result = await run_sync(
                active_service.chat, identity, request.headers, body, started
            )
        except (EdgeError, DownstreamError):
            raise
        if isinstance(result, CompletionResult):
            return JSONResponse(result.payload)
        assert isinstance(result, StreamingResult)
        return StreamingResponse(
            _async_stream(result.body),
            media_type="text/event-stream",
        )

    async def rest_forward(request: Request):
        started = time.monotonic()
        identity = await _authenticate(active_service, request, started, "rest")
        capability_path = request.path_params["capability_path"].strip("/")
        capability = capability_path.replace("/", ".")
        raw = await request.body()
        if raw:
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                active_service.audit_resolved_failure(identity, started)
                raise RequestValidationError(
                    "el cuerpo no contiene JSON valido", "body"
                ) from exc
            if not isinstance(payload, dict):
                active_service.audit_resolved_failure(identity, started)
                raise RequestValidationError(
                    "el cuerpo JSON debe ser un objeto", "body"
                )
        else:
            payload = {}
        identity_overridden = "identity" in payload
        result = await run_sync(
            lambda: active_service.forward_rest(
                identity,
                method=request.method,
                capability=capability,
                query=request.url.query,
                payload=payload,
                identity_overridden=identity_overridden,
                started=started,
            )
        )
        if isinstance(result, ForwardedJson):
            return JSONResponse(result.payload, status_code=result.status_code)
        assert isinstance(result, ForwardedStream)
        return StreamingResponse(
            _async_stream(result.body),
            status_code=result.status_code,
            headers={"content-type": result.content_type},
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
        return JSONResponse({"error": exc.error}, status_code=exc.status_code)

    routes = [
        Route("/v1/models", models, methods=["GET"]),
        Route("/v1/chat/completions", chat_completions, methods=["POST"]),
        Route(
            "/rest/{capability_path:path}",
            rest_forward,
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        ),
        Mount("/", app=mcp_app),
    ]
    app = Starlette(
        routes=routes,
        exception_handlers={
            EdgeError: edge_error_handler,
            DownstreamError: downstream_error_handler,
        },
        lifespan=lifespan,
    )
    app.add_middleware(_McpAuthenticationMiddleware, service=active_service)
    return app


class _McpAuthenticationMiddleware:
    def __init__(self, app, service: EdgeService) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or path in {
            "/v1/models",
            "/v1/chat/completions",
        } or path.startswith("/rest/"):
            await self.app(scope, receive, send)
            return
        from starlette.datastructures import Headers
        from starlette.responses import JSONResponse

        started = time.monotonic()
        headers = Headers(scope=scope)
        try:
            identity = await run_sync(
                self.service.authenticate_and_resolve,
                headers.get("authorization"),
                headers,
            )
        except AuthenticationError as exc:
            await run_sync(
                self.service.audit_access_failure,
                "mcp",
                "authentication_failed",
                started,
            )
            response = JSONResponse(
                {"error": exc.to_dict()},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        except AuthorizationError as exc:
            await run_sync(
                self.service.audit_access_failure, "mcp", "forbidden", started
            )
            await JSONResponse(
                {"error": exc.to_dict()}, status_code=403
            )(scope, receive, send)
            return
        except DirectoryUnavailableError as exc:
            await run_sync(
                self.service.audit_access_failure,
                "mcp",
                "directory_unavailable",
                started,
            )
            await JSONResponse(
                {"error": exc.to_dict()}, status_code=503
            )(scope, receive, send)
            return
        scope.setdefault("state", {})["edge_identity"] = identity
        await self.app(scope, receive, send)


async def _authenticate(
    service: EdgeService, request, started: float, face: str
):
    try:
        return await run_sync(
            service.authenticate_and_resolve,
            request.headers.get("authorization"),
            request.headers,
        )
    except AuthenticationError:
        await run_sync(
            service.audit_access_failure, face, "authentication_failed", started
        )
        raise
    except AuthorizationError:
        await run_sync(
            service.audit_access_failure, face, "forbidden", started
        )
        raise
    except DirectoryUnavailableError:
        await run_sync(
            service.audit_access_failure, face, "directory_unavailable", started
        )
        raise


def _close_stream(body) -> None:
    close = getattr(body, "close", None)
    if close is not None:
        close()


_STREAM_END = object()


def _next_stream_item(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return _STREAM_END


async def _async_stream(body):
    iterator = iter(body)
    try:
        while True:
            item = await run_sync(_next_stream_item, iterator)
            if item is _STREAM_END:
                return
            yield item
    finally:
        _close_stream(iterator)

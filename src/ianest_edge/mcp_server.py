"""Servidor MCP dinamico sobre el catalogo uniforme de extended."""

from __future__ import annotations

import json
import time
from typing import Any

from .async_utils import run_sync
from .client import ForwardedJson, ForwardedStream
from .errors import CapabilityNotAllowedError, EdgeError, ExtendedResponseError
from .identity import ResolvedIdentity
from .service import EdgeService

_JSON_TYPES = {
    "string": "string",
    "integer": "integer",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


def create_mcp_app(service: EdgeService):
    try:
        from mcp.server.lowlevel import Server
        from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
    except ImportError as exc:  # pragma: no cover - dependencia obligatoria
        raise RuntimeError("mcp no esta instalado") from exc

    async def list_tools(ctx, params):
        identity = _request_identity(ctx)
        started = time.monotonic()
        try:
            catalog = await run_sync(service.capability_catalog)
            declarations = _exposed_capabilities(
                catalog, service.config.allowed_capabilities
            )
            tools = [
                Tool(
                    name=item["name"],
                    description=str(item.get("summary", "")),
                    inputSchema=_input_schema(item),
                )
                for item in declarations
            ]
        except BaseException:
            await run_sync(
                service.audit_mcp, identity, "capability.list", "error", started
            )
            raise
        await run_sync(
            service.audit_mcp, identity, "capability.list", "ok", started
        )
        return ListToolsResult(tools=tools)

    async def call_tool(ctx, params):
        identity = _request_identity(ctx)
        started = time.monotonic()
        capability = params.name
        supplied = dict(params.arguments or {})
        overridden = service.identity_overridden(supplied)
        if capability not in service.config.allowed_capabilities:
            error = CapabilityNotAllowedError(
                f"la capacidad {capability!r} no esta permitida", "capability"
            )
            await run_sync(
                lambda: service.audit_mcp(
                    identity,
                    capability,
                    "capability_not_allowed",
                    started,
                    identity_overridden=overridden,
                )
            )
            return _error_result(CallToolResult, TextContent, error.to_dict())
        try:
            catalog = await run_sync(service.capability_catalog)
            declaration = next(
                (
                    item
                    for item in _exposed_capabilities(
                        catalog, service.config.allowed_capabilities
                    )
                    if item["name"] == capability
                ),
                None,
            )
            if declaration is None:
                raise ExtendedResponseError(
                    f"extended no declara {capability!r} como herramienta MCP"
                )
            rest = declaration["rest"]
            result = await run_sync(
                lambda: service.forward_rest(
                    identity,
                    method=str(rest["method"]).upper(),
                    capability=capability,
                    route=str(rest["path"]),
                    query="",
                    payload=supplied,
                    started=started,
                    face="mcp",
                )
            )
        except EdgeError as exc:
            if not isinstance(exc, CapabilityNotAllowedError):
                await run_sync(
                    lambda: service.audit_mcp(
                        identity,
                        capability,
                        "error",
                        started,
                        identity_overridden=overridden,
                    )
                )
            return _error_result(CallToolResult, TextContent, exc.to_dict())
        if isinstance(result, ForwardedStream):
            close = getattr(result.body, "close", None)
            if close is not None:
                close()
            error = ExtendedResponseError(
                f"{capability!r} devolvio streaming, que MCP no expone"
            )
            return _error_result(CallToolResult, TextContent, error.to_dict())
        assert isinstance(result, ForwardedJson)
        payload = result.payload
        is_error = result.status_code >= 400
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(payload, ensure_ascii=True, sort_keys=True),
                )
            ],
            isError=is_error,
        )

    server = Server(
        "ia_nest_edge",
        version="0.2.1",
        instructions=(
            "Herramientas derivadas de capability.list y limitadas por la "
            "configuracion del borde. La identidad la afirma el borde."
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        host=service.config.host,
    )


def _request_identity(ctx) -> ResolvedIdentity:
    request = ctx.request
    if request is None:
        raise RuntimeError("MCP no recibio contexto HTTP")
    identity = request.scope.get("state", {}).get("edge_identity")
    if not isinstance(identity, ResolvedIdentity):
        raise RuntimeError("MCP no recibio identidad autenticada")
    return identity


def _catalog_items(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    raw = catalog.get("capabilities")
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ExtendedResponseError(
            "capability.list no devolvio capabilities como lista"
        )
    return raw


def _exposed_capabilities(
    catalog: dict[str, Any], allowed: tuple[str, ...]
) -> list[dict[str, Any]]:
    allowed_set = set(allowed)
    result = []
    for item in _catalog_items(catalog):
        name = item.get("name")
        if (
            isinstance(name, str)
            and name in allowed_set
            and not item.get("streaming")
            and isinstance(item.get("mcp"), dict)
            and isinstance(item.get("rest"), dict)
            and isinstance(item["rest"].get("method"), str)
            and isinstance(item["rest"].get("path"), str)
        ):
            result.append(item)
    return sorted(result, key=lambda item: item["name"])


def _input_schema(capability: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    parameters = capability.get("params", [])
    if not isinstance(parameters, list):
        parameters = []
    for declaration in parameters:
        if not isinstance(declaration, dict):
            continue
        name = declaration.get("name")
        type_name = declaration.get("type")
        if not isinstance(name, str) or type_name not in _JSON_TYPES:
            continue
        schema: dict[str, Any] = {"type": _JSON_TYPES[type_name]}
        summary = declaration.get("summary")
        if isinstance(summary, str):
            schema["description"] = summary
        choices = declaration.get("choices")
        if isinstance(choices, list) and choices:
            schema["enum"] = choices
        default = declaration.get("default")
        if default is not None:
            schema["default"] = default
        properties[name] = schema
        if declaration.get("required"):
            required.append(name)
    schema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _error_result(call_type, text_type, error: dict[str, Any]):
    return call_type(
        content=[
            text_type(
                type="text",
                text=json.dumps(
                    {"error": error}, ensure_ascii=True, sort_keys=True
                ),
            )
        ],
        isError=True,
    )

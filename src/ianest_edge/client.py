"""Cliente HTTP del contrato REST de ia_nest_extended."""

from __future__ import annotations

import json
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from typing import Any, Iterator, Protocol
from urllib.parse import urlsplit

from .errors import DownstreamError, ExtendedConnectionError, ExtendedResponseError

EXTENDED_ORIGIN = "ia_nest_extended"


@dataclass(frozen=True, slots=True)
class SseEvent:
    event: str | None
    data: Any


@dataclass(frozen=True, slots=True)
class ForwardedJson:
    payload: Any
    status_code: int
    content_type: str | None


@dataclass(frozen=True, slots=True)
class ForwardedStream:
    body: Iterator[bytes]
    status_code: int
    content_type: str


class ExtendedClient(Protocol):
    def domain_list(self) -> dict[str, Any]: ...

    def capability_list(self) -> dict[str, Any]: ...

    def session_list(
        self, identity: dict[str, str], status: str
    ) -> dict[str, Any]: ...

    def session_new(
        self, identity: dict[str, str], session_id: str | None = None
    ) -> dict[str, Any]: ...

    def run(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def stream(
        self, capability: str, payload: dict[str, Any]
    ) -> Iterator[SseEvent]: ...

    def forward(
        self,
        method: str,
        route: str,
        *,
        query: str = "",
        payload: dict[str, Any],
    ) -> ForwardedJson | ForwardedStream: ...


class ExtendedHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        connect_timeout_seconds: float = 30.0,
        inactivity_timeout_seconds: float = 600.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._connect_timeout = connect_timeout_seconds
        self._inactivity_timeout = inactivity_timeout_seconds

    def domain_list(self) -> dict[str, Any]:
        return self._json("GET", "/domain/list", None)

    def capability_list(self) -> dict[str, Any]:
        return self._json("GET", "/capability/list", None)

    def session_list(
        self, identity: dict[str, str], status: str
    ) -> dict[str, Any]:
        return self._json(
            "POST", "/session/list", {"identity": identity, "status": status}
        )

    def session_new(
        self, identity: dict[str, str], session_id: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"identity": identity}
        if session_id is not None:
            payload["session_id"] = session_id
        return self._json("POST", "/session/new", payload)

    def run(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", _route(capability), payload)

    def stream(
        self, capability: str, payload: dict[str, Any]
    ) -> Iterator[SseEvent]:
        connection, response = self._open(
            "POST", _route(capability), json.dumps(payload).encode("utf-8"),
            "application/json"
        )
        try:
            _raise_for_status(response)
            response_content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" not in response_content_type:
                raise ExtendedResponseError(
                    f"{capability} no devolvio text/event-stream"
                )
        except BaseException:
            connection.close()
            raise

        def events() -> Iterator[SseEvent]:
            try:
                for raw in _raw_sse_events(response):
                    lines = raw.decode("utf-8", errors="replace").splitlines()
                    yield _parse_sse(lines)
            except (OSError, TimeoutError, HTTPException) as exc:
                raise ExtendedConnectionError(
                    f"se interrumpio el flujo de extended: {exc}"
                ) from exc
            finally:
                connection.close()

        return events()

    def forward(
        self,
        method: str,
        route: str,
        *,
        query: str = "",
        payload: dict[str, Any],
    ) -> ForwardedJson | ForwardedStream:
        target = route + (f"?{query}" if query else "")
        body = json.dumps(payload).encode("utf-8")
        request_content_type = "application/json"
        connection, response = self._open(
            method, target, body, request_content_type
        )
        response_content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" in response_content_type:
            def stream() -> Iterator[bytes]:
                try:
                    yield from _raw_sse_events(response)
                except (OSError, TimeoutError, HTTPException) as exc:
                    raise ExtendedConnectionError(
                        f"se interrumpio el flujo de extended: {exc}"
                    ) from exc
                finally:
                    connection.close()

            return ForwardedStream(
                body=stream(),
                status_code=response.status,
                content_type=response_content_type,
            )
        try:
            raw = response.read()
        except (OSError, TimeoutError, HTTPException) as exc:
            raise ExtendedConnectionError(
                f"no se pudo leer la respuesta de extended: {exc}"
            ) from exc
        finally:
            connection.close()
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExtendedResponseError("extended no devolvio JSON valido") from exc
        return ForwardedJson(
            payload=value,
            status_code=response.status,
            content_type=response_content_type or None,
        )

    def _json(
        self,
        method: str,
        route: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        connection, response = self._open(
            method,
            route,
            body,
            "application/json" if body is not None else None,
        )
        try:
            _raise_for_status(response)
            raw = response.read()
        except (OSError, TimeoutError, HTTPException) as exc:
            raise ExtendedConnectionError(
                f"no se pudo leer la respuesta de extended: {exc}"
            ) from exc
        finally:
            connection.close()
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExtendedResponseError("extended no devolvio JSON valido") from exc
        if not isinstance(value, dict):
            raise ExtendedResponseError("extended no devolvio un objeto JSON")
        return value

    def _open(
        self,
        method: str,
        route: str,
        body: bytes | None,
        content_type: str | None,
    ):
        parts = urlsplit(self._base_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ExtendedConnectionError("extended.base_url no es una URL HTTP valida")
        factory = HTTPSConnection if parts.scheme == "https" else HTTPConnection
        connection = factory(
            parts.hostname, parts.port, timeout=self._connect_timeout
        )
        base_path = parts.path.rstrip("/")
        target = f"{base_path}{route}" or "/"
        headers = {"Accept": "application/json, text/event-stream"}
        if body is not None and content_type:
            headers["Content-Type"] = content_type
        try:
            connection.request(method, target, body=body, headers=headers)
            if connection.sock is not None:
                connection.sock.settimeout(self._inactivity_timeout)
            response = connection.getresponse()
        except (OSError, TimeoutError, HTTPException) as exc:
            connection.close()
            raise ExtendedConnectionError(
                f"no se pudo conectar con extended: {exc}"
            ) from exc
        return connection, response


def _route(capability: str) -> str:
    return "/" + capability.replace(".", "/")


def _raise_for_status(response) -> None:
    if response.status < 400:
        return
    raw = response.read()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = None
    error = None
    if isinstance(value, dict):
        candidate = value.get("error", value)
        if isinstance(candidate, dict) and candidate.get("type"):
            error = dict(candidate)
    if error is not None:
        error.setdefault("origin", EXTENDED_ORIGIN)
        raise DownstreamError(error, response.status)
    detail = raw.decode("utf-8", errors="replace")[:500]
    raise ExtendedResponseError(
        f"extended devolvio HTTP {response.status}: {detail}"
    )


def _raw_sse_events(response) -> Iterator[bytes]:
    block: list[bytes] = []
    for raw_line in response:
        line = raw_line.rstrip(b"\r\n")
        if line:
            block.append(line)
        elif block:
            yield b"\n".join(block) + b"\n\n"
            block = []
    if block:
        yield b"\n".join(block) + b"\n\n"


def _parse_sse(lines: list[str]) -> SseEvent:
    event = None
    data_lines = []
    for line in lines:
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "event":
            event = value
        elif name == "data":
            data_lines.append(value)
    raw_data = "\n".join(data_lines)
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError:
        data = raw_data
    return SseEvent(event=event, data=data)

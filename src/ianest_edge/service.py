"""Aplicacion del borde: autentica, resuelve, traduce y audita."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .audit import AuditRecord, AuditWriter
from .client import ExtendedClient, ExtendedHttpClient, SseEvent
from .config import EdgeConfig, MenuEntry, PROFILE_CHILD
from .errors import ConfigurationError, DownstreamError, RequestValidationError
from .identity import IdentityResolver, ResolvedIdentity

INTERLOCUTOR_PROFILE_FIELD = "interlocutor_profile"


@dataclass(frozen=True, slots=True)
class CompletionResult:
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StreamingResult:
    body: Iterator[bytes]


@dataclass(slots=True)
class _AuditState:
    consumer: str | None = None
    user_id: str | None = None
    profile: str | None = None
    menu_entry: str | None = None
    mode: str | None = None
    capability: str | None = None
    session_id: str | None = None
    background_task: bool = False
    system_messages: int = 0
    finish_reason: str | None = None


class EdgeService:
    def __init__(
        self,
        config: EdgeConfig,
        *,
        resolver: IdentityResolver,
        client: ExtendedClient | None = None,
        audit: AuditWriter | None = None,
    ) -> None:
        self.config = config
        self.resolver = resolver
        self.client = client or ExtendedHttpClient(
            config.extended_url,
            connect_timeout_seconds=config.connect_timeout_seconds,
            inactivity_timeout_seconds=config.inactivity_timeout_seconds,
        )
        self.audit = audit or AuditWriter(config.audit_path)

    def validate_startup(self) -> None:
        """Comprueba conectividad y toda restriccion que depende de dominios."""
        response = self.client.domain_list()
        domains_raw = response.get("domains")
        if not isinstance(domains_raw, list):
            raise ConfigurationError(
                "domain.list no devolvio domains como lista", "extended.base_url"
            )
        domain_ids = {
            item.get("id")
            for item in domains_raw
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if len(domain_ids) != len(domains_raw):
            raise ConfigurationError(
                "domain.list contiene una entrada sin id", "extended.base_url"
            )
        for field, identity in self._configured_identities():
            if identity.profile == PROFILE_CHILD:
                invalid = next(
                    (entry for entry in identity.menu if entry.mode != "directo"),
                    None,
                )
                if invalid is not None:
                    raise ConfigurationError(
                        "una identidad child solo puede usar modo directo",
                        f"{field}.menu.{invalid.id}.mode",
                    )
            for entry in identity.menu:
                if entry.mode == "iterativo" and entry.domain != "auto":
                    raise ConfigurationError(
                        "una entrada iterativo debe usar domain=auto",
                        f"{field}.menu.{entry.id}.domain",
                    )
                if entry.domain != "auto" and entry.domain not in domain_ids:
                    raise ConfigurationError(
                        f"el dominio {entry.domain!r} no existe en domain.list",
                        f"{field}.menu.{entry.id}.domain",
                    )

    def authenticate_and_resolve(
        self,
        authorization: str | None,
        headers: Mapping[str, str],
    ) -> ResolvedIdentity:
        consumer = self.resolver.authenticate(authorization)
        return self.resolver.resolve(consumer, headers)

    def audit_authentication_failure(self, started: float) -> None:
        self._write_audit(_AuditState(), "error", started)

    def audit_resolved_failure(
        self,
        identity: ResolvedIdentity,
        started: float,
    ) -> None:
        self._write_audit(_state_for(identity), "error", started)

    def models(self, identity: ResolvedIdentity, started: float) -> dict[str, Any]:
        state = _state_for(identity)
        try:
            data = [
                {
                    "id": entry.id,
                    "object": "model",
                    "created": 0,
                    "owned_by": "ia_nest_edge",
                }
                for entry in identity.menu
            ]
            data.append(
                {
                    "id": "ia_nest",
                    "object": "model",
                    "created": 0,
                    "owned_by": "ia_nest_edge",
                }
            )
            self._write_audit(state, "ok", started)
            return {"object": "list", "data": data}
        except BaseException:
            self._write_audit(state, "error", started)
            raise

    def chat(
        self,
        identity: ResolvedIdentity,
        headers: Mapping[str, str],
        body: Any,
        started: float,
    ) -> CompletionResult | StreamingResult:
        state = _state_for(identity)
        try:
            request = _validate_chat_body(body)
            state.system_messages = sum(
                item["role"] in {"system", "developer"}
                for item in request["messages"]
            )
            entry = _select_entry(identity, request["model"])
            state.menu_entry = entry.id
            state.mode = entry.mode
            state.background_task = _header_present(
                headers, identity.consumer.headers.background_task
            )
            prompt = _last_user_message(request["messages"])
            base_identity = _identity_payload(identity)
            session_id = self._resolve_session(
                identity,
                headers,
                base_identity,
                request["messages"],
            )
            state.session_id = session_id
            capability = _capability(entry, request["stream"])
            state.capability = capability
            payload: dict[str, Any] = {
                "prompt": prompt,
                "identity": {**base_identity, "session_id": session_id},
            }
            if entry.mode != "iterativo":
                if entry.domain == "auto":
                    payload["auto_domain"] = True
                else:
                    payload["domain"] = entry.domain
            if state.background_task or not identity.consumer.write_memory:
                payload["write_back"] = False
            visible_model = request["model"]
            if entry.mode == "iterativo" or not request["stream"]:
                downstream = self.client.run(capability, payload)
                raw_finish = _raw_finish_reason(downstream)
                state.finish_reason = raw_finish
                response = _completion_payload(
                    downstream,
                    visible_model,
                    raw_finish,
                )
                if request["stream"]:
                    return StreamingResult(
                        self._single_chunk_stream(response, state, started)
                    )
                self._write_audit(state, "ok", started)
                return CompletionResult(response)
            downstream_events = self.client.stream(capability, payload)
            return StreamingResult(
                self._translated_stream(
                    downstream_events,
                    visible_model,
                    state,
                    started,
                )
            )
        except BaseException:
            self._write_audit(state, "error", started)
            raise

    def _resolve_session(
        self,
        identity: ResolvedIdentity,
        headers: Mapping[str, str],
        base_identity: dict[str, str],
        messages: list[dict[str, str]],
    ) -> str:
        chat_id = _header_value(headers, identity.consumer.headers.chat)
        if chat_id is not None:
            prefix = f"{identity.consumer.name}-{chat_id}-"
            active = _sessions(
                self.client.session_list(base_identity, "activa")
            )
            active_numbers = _session_numbers(active, prefix)
            if active_numbers:
                return f"{prefix}{max(active_numbers)}"
            all_sessions = _sessions(
                self.client.session_list(base_identity, "todas")
            )
            all_numbers = _session_numbers(all_sessions, prefix)
            selected = f"{prefix}{max(all_numbers, default=0) + 1}"
            try:
                return _new_session_id(
                    self.client.session_new(base_identity, selected)
                )
            except DownstreamError as exc:
                if not _is_duplicate_session_error(exc):
                    raise
                active = _sessions(
                    self.client.session_list(base_identity, "activa")
                )
                active_numbers = _session_numbers(active, prefix)
                if active_numbers:
                    return f"{prefix}{max(active_numbers)}"
                raise

        user_messages = sum(item["role"] == "user" for item in messages)
        if user_messages == 1:
            return _new_session_id(self.client.session_new(base_identity))
        active = _sessions(self.client.session_list(base_identity, "activa"))
        if not active:
            return _new_session_id(self.client.session_new(base_identity))
        latest = max(
            active,
            key=lambda item: (
                _activity_timestamp(item),
                str(item.get("session_id", "")),
            ),
        )
        session_id = latest.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise RequestValidationError(
                "session.list devolvio una sesion sin session_id"
            )
        return session_id

    def _single_chunk_stream(
        self,
        completion: dict[str, Any],
        state: _AuditState,
        started: float,
    ) -> Iterator[bytes]:
        choice = completion["choices"][0]
        chunk = _chunk(
            completion["id"],
            completion["created"],
            completion["model"],
            {"role": "assistant", "content": choice["message"]["content"]},
            choice["finish_reason"],
        )
        try:
            yield _sse(chunk)
            yield b"data: [DONE]\n\n"
        except GeneratorExit:
            self._write_audit(state, "interrupted", started)
            raise
        except BaseException:
            self._write_audit(state, "error", started)
            raise
        else:
            self._write_audit(state, "ok", started)

    def _translated_stream(
        self,
        events: Iterator[SseEvent],
        model: str,
        state: _AuditState,
        started: float,
    ) -> Iterator[bytes]:
        completion_id = f"chatcmpl-{uuid4().hex}"
        created = int(time.time())
        emitted_content = False
        final_usage = None
        try:
            for event in events:
                event_type, data = _event_data(event)
                if event_type in {"token", "answer_chunk"}:
                    text = data.get("text")
                    if isinstance(text, str) and text:
                        emitted_content = True
                        yield _sse(
                            _chunk(
                                completion_id,
                                created,
                                model,
                                {"content": text},
                                None,
                            )
                        )
                elif event_type == "error":
                    error = data if isinstance(data, dict) else {}
                    error.setdefault("origin", "ia_nest_extended")
                    raise DownstreamError(error, 502)
                elif event_type == "done":
                    if not emitted_content:
                        text = _response_text(data)
                        if text:
                            emitted_content = True
                            yield _sse(
                                _chunk(
                                    completion_id,
                                    created,
                                    model,
                                    {"content": text},
                                    None,
                                )
                            )
                    state.finish_reason = _raw_finish_reason(data)
                    if isinstance(data.get("usage"), dict):
                        final_usage = data["usage"]
            finish = _translate_finish_reason(state.finish_reason)
            final = _chunk(completion_id, created, model, {}, finish)
            if final_usage is not None:
                final["usage"] = final_usage
            yield _sse(final)
            yield b"data: [DONE]\n\n"
        except GeneratorExit:
            self._write_audit(state, "interrupted", started)
            raise
        except DownstreamError as exc:
            self._write_audit(state, "error", started)
            yield _sse({"error": exc.error})
        except EdgeError as exc:
            self._write_audit(state, "error", started)
            yield _sse({"error": exc.to_dict()})
        except BaseException:
            self._write_audit(state, "error", started)
            raise
        else:
            self._write_audit(state, "ok", started)

    def _configured_identities(self):
        yield "guest", self.config.guest
        for consumer in self.config.consumers:
            base = f"consumers.{consumer.name}"
            yield f"{base}.default_identity", consumer.default_identity
            for person, identity in consumer.people.items():
                yield f"{base}.people.{person}", identity

    def _write_audit(
        self,
        state: _AuditState,
        outcome: str,
        started: float,
    ) -> None:
        self.audit.write(
            AuditRecord(
                consumer=state.consumer,
                user_id=state.user_id,
                interlocutor_profile=state.profile,
                menu_entry=state.menu_entry,
                mode=state.mode,
                capability=state.capability,
                session_id=state.session_id,
                background_task=state.background_task,
                discarded_system_messages=state.system_messages,
                outcome=outcome,
                finish_reason=state.finish_reason,
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )
        )


def _state_for(identity: ResolvedIdentity) -> _AuditState:
    return _AuditState(
        consumer=identity.consumer.name,
        user_id=identity.user_id,
        profile=identity.interlocutor_profile,
    )


def _validate_chat_body(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise RequestValidationError("el cuerpo debe ser un objeto JSON", "body")
    if body.get("tools") not in (None, []):
        raise RequestValidationError(
            "tools no esta soportado por esta superficie", "tools"
        )
    if body.get("functions") not in (None, []):
        raise RequestValidationError(
            "functions no esta soportado por esta superficie", "functions"
        )
    model = body.get("model")
    if not isinstance(model, str) or not model:
        raise RequestValidationError("model es obligatorio", "model")
    stream = body.get("stream", False)
    if not isinstance(stream, bool):
        raise RequestValidationError("stream debe ser booleano", "stream")
    messages_raw = body.get("messages")
    if not isinstance(messages_raw, list) or not messages_raw:
        raise RequestValidationError(
            "messages debe ser una lista no vacia", "messages"
        )
    messages = []
    for index, item in enumerate(messages_raw):
        if not isinstance(item, dict):
            raise RequestValidationError(
                "cada mensaje debe ser un objeto", f"messages[{index}]"
            )
        role = item.get("role")
        content = item.get("content")
        if role not in {"system", "developer", "user", "assistant"}:
            raise RequestValidationError(
                "role no esta soportado", f"messages[{index}].role"
            )
        content = _message_content(content, index)
        messages.append({"role": role, "content": content})
    return {"model": model, "stream": stream, "messages": messages}


def _last_user_message(messages: list[dict[str, str]]) -> str:
    for item in reversed(messages):
        if item["role"] == "user":
            return item["content"]
    raise RequestValidationError(
        "messages debe contener al menos un mensaje de usuario", "messages"
    )


def _message_content(content: Any, message_index: int) -> str:
    if isinstance(content, str):
        return content
    field = f"messages[{message_index}].content"
    if not isinstance(content, list):
        raise RequestValidationError("content debe ser texto o lista de partes", field)
    text_parts = []
    for part_index, part in enumerate(content):
        part_field = f"{field}[{part_index}]"
        if not isinstance(part, dict):
            raise RequestValidationError("cada parte debe ser un objeto", part_field)
        if part.get("type") != "text":
            raise RequestValidationError(
                "solo se soportan partes content de type text", part_field
            )
        text = part.get("text")
        if not isinstance(text, str):
            raise RequestValidationError("la parte text debe contener texto", part_field)
        text_parts.append(text)
    return "\n".join(text_parts)


def _select_entry(identity: ResolvedIdentity, model: str) -> MenuEntry:
    if model == "ia_nest":
        return identity.default_entry
    for entry in identity.menu:
        if entry.id == model:
            return entry
    raise RequestValidationError(
        f"el modelo {model!r} no esta en el menu de esta identidad", "model"
    )


def _capability(entry: MenuEntry, stream: bool) -> str:
    if entry.mode == "directo":
        return "prompt.stream" if stream else "prompt.run"
    if entry.mode == "razonado":
        return "reasoning.stream" if stream else "reasoning.run"
    return "task.run"


def _identity_payload(identity: ResolvedIdentity) -> dict[str, str]:
    return {
        "user_id": identity.user_id,
        "service": identity.service,
        INTERLOCUTOR_PROFILE_FIELD: identity.interlocutor_profile,
    }


def _sessions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sessions = payload.get("sessions")
    if not isinstance(sessions, list) or not all(
        isinstance(item, dict) for item in sessions
    ):
        raise RequestValidationError("session.list devolvio una forma invalida")
    return sessions


def _session_numbers(sessions: list[dict[str, Any]], prefix: str) -> list[int]:
    values = []
    for session in sessions:
        session_id = session.get("session_id")
        if not isinstance(session_id, str) or not session_id.startswith(prefix):
            continue
        suffix = session_id[len(prefix) :]
        if suffix.isdigit() and int(suffix) > 0:
            values.append(int(suffix))
    return values


def _new_session_id(payload: dict[str, Any]) -> str:
    session = payload.get("session")
    if not isinstance(session, dict):
        raise RequestValidationError("session.new no devolvio session")
    session_id = session.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise RequestValidationError("session.new no devolvio session_id")
    return session_id


def _is_duplicate_session_error(exc: DownstreamError) -> bool:
    return exc.error.get("type") == "SessionAlreadyExistsError"


def _activity_timestamp(session: dict[str, Any]) -> float:
    value = session.get("last_activity_at")
    if not isinstance(value, str):
        return float("-inf")
    try:
        return datetime.fromisoformat(value).astimezone(UTC).timestamp()
    except ValueError:
        return float("-inf")


def _completion_payload(
    downstream: dict[str, Any],
    model: str,
    raw_finish: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": _response_text(downstream),
                },
                "finish_reason": _translate_finish_reason(raw_finish),
            }
        ],
    }
    if isinstance(downstream.get("usage"), dict):
        payload["usage"] = downstream["usage"]
    return payload


def _response_text(payload: Mapping[str, Any]) -> str:
    for key in ("response", "output", "text"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        return _response_text(data)
    raise RequestValidationError("extended no devolvio texto de respuesta")


def _raw_finish_reason(payload: Mapping[str, Any]) -> str | None:
    for key in ("finish_reason", "stop_reason"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    trace = payload.get("trace")
    if isinstance(trace, dict):
        for key in ("finish_reason", "stop_reason"):
            value = trace.get(key)
            if value is not None:
                return str(value)
    return None


def _translate_finish_reason(reason: str | None) -> str:
    if reason == "length" or reason == "incomplete":
        return "length"
    return "stop"


def _event_data(event: SseEvent) -> tuple[str | None, dict[str, Any]]:
    data = event.data if isinstance(event.data, dict) else {}
    event_type = event.event
    if event_type is None and isinstance(data.get("type"), str):
        event_type = data["type"]
    nested = data.get("data")
    if isinstance(nested, dict):
        data = nested
    return event_type, data


def _chunk(
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None,
) -> dict[str, Any]:
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


def _sse(payload: dict[str, Any]) -> bytes:
    return (
        "data: "
        + json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        + "\n\n"
    ).encode("ascii")


def _header_value(headers: Mapping[str, str], name: str | None) -> str | None:
    if name is None:
        return None
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def _header_present(headers: Mapping[str, str], name: str | None) -> bool:
    value = _header_value(headers, name)
    return value is not None and bool(value.strip())

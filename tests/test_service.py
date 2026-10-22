from __future__ import annotations

import json
import time

import pytest

from ianest_edge.errors import DownstreamError, RequestValidationError
from ianest_edge.client import SseEvent
from ianest_edge.service import CompletionResult, StreamingResult

from .conftest import KEY


def _identity(service, person="adult"):
    return service.authenticate_and_resolve(
        f"Bearer {KEY}", {"X-Person": person}
    )


def _body(model="direct", *, stream=False, messages=None, **extra):
    return {
        "model": model,
        "stream": stream,
        "messages": messages or [{"role": "user", "content": "pregunta"}],
        **extra,
    }


def _audit(config):
    return [
        json.loads(line)
        for line in config.audit_path.read_text(encoding="ascii").splitlines()
    ]


def test_models_contains_exact_menu_plus_alias(service):
    payload = service.models(_identity(service), time.monotonic())

    assert [item["id"] for item in payload["data"]] == [
        "direct",
        "reasoned",
        "iterative",
        "ia_nest",
    ]


def test_unknown_model_is_rejected_without_inference_call(service, extended):
    with pytest.raises(RequestValidationError, match="no esta en el menu"):
        service.chat(
            _identity(service), {}, _body(model="outside"), time.monotonic()
        )

    assert not any(call[0] in {"prompt.run", "reasoning.run", "task.run"} for call in extended.calls)


def test_only_last_user_message_reaches_extended_and_system_is_audited(
    service, extended, config
):
    messages = [
        {"role": "system", "content": "secreto-sistema"},
        {"role": "user", "content": "primero"},
        {"role": "assistant", "content": "anterior"},
        {"role": "user", "content": "ultimo"},
    ]

    result = service.chat(
        _identity(service), {}, _body(messages=messages), time.monotonic()
    )

    assert isinstance(result, CompletionResult)
    run_call = next(call for call in extended.calls if call[0] == "prompt.run")
    assert run_call[1]["prompt"] == "ultimo"
    encoded = json.dumps(run_call)
    assert "secreto-sistema" not in encoded
    assert "primero" not in encoded
    audit = _audit(config)[-1]
    assert audit["discarded_system_messages"] == 1
    assert "secreto-sistema" not in config.audit_path.read_text(encoding="ascii")


def test_child_profile_is_forwarded_and_audited(service, extended, config):
    result = service.chat(
        _identity(service, "child"),
        {},
        _body(model="child_direct"),
        time.monotonic(),
    )

    assert isinstance(result, CompletionResult)
    run_call = next(call for call in extended.calls if call[0] == "prompt.run")
    assert run_call[1]["identity"]["interlocutor_profile"] == "child"
    assert _audit(config)[-1]["interlocutor_profile"] == "child"


@pytest.mark.parametrize("person", [None, "nobody", "unknown_profile"])
def test_all_unknown_person_paths_forward_child(service, extended, person):
    headers = {} if person is None else {"X-Person": person}
    identity = service.authenticate_and_resolve(f"Bearer {KEY}", headers)
    service.chat(
        identity,
        headers,
        _body(model="child_direct"),
        time.monotonic(),
    )
    run_call = next(call for call in reversed(extended.calls) if call[0] == "prompt.run")
    assert run_call[1]["identity"]["interlocutor_profile"] == "child"


def test_fixed_and_auto_domain_translation(service, extended):
    identity = _identity(service)
    service.chat(identity, {}, _body(model="direct"), time.monotonic())
    service.chat(identity, {}, _body(model="reasoned"), time.monotonic())

    direct = next(call for call in extended.calls if call[0] == "prompt.run")
    reasoned = next(call for call in extended.calls if call[0] == "reasoning.run")
    assert direct[1]["domain"] == "linux"
    assert "auto_domain" not in direct[1]
    assert reasoned[1]["auto_domain"] is True
    assert "domain" not in reasoned[1]


def test_iterative_never_receives_domain_and_streams_one_chunk(
    service, extended
):
    result = service.chat(
        _identity(service),
        {},
        _body(model="iterative", stream=True),
        time.monotonic(),
    )

    assert isinstance(result, StreamingResult)
    task_call = next(call for call in extended.calls if call[0] == "task.run")
    assert "domain" not in task_call[1]
    assert "auto_domain" not in task_call[1]
    chunks = list(result.body)
    assert len(chunks) == 2
    assert b'"content":"respuesta"' in chunks[0]
    assert chunks[1] == b"data: [DONE]\n\n"


def test_background_task_disables_write_back(service, extended):
    service.chat(
        _identity(service),
        {"X-Task": "anything"},
        _body(),
        time.monotonic(),
    )

    run_call = next(call for call in extended.calls if call[0] == "prompt.run")
    assert run_call[1]["write_back"] is False


@pytest.mark.parametrize("field", ["tools", "functions"])
def test_tools_and_functions_are_explicit_errors(service, extended, field):
    with pytest.raises(RequestValidationError, match=field):
        service.chat(
            _identity(service),
            {},
            _body(**{field: [{"type": "function"}]}),
            time.monotonic(),
        )
    assert not any(call[0] == "prompt.run" for call in extended.calls)


@pytest.mark.parametrize("field", ["tools", "functions"])
@pytest.mark.parametrize("value", [None, []])
def test_empty_tools_and_functions_are_accepted(service, field, value):
    result = service.chat(
        _identity(service), {}, _body(**{field: value}), time.monotonic()
    )

    assert isinstance(result, CompletionResult)


def test_developer_message_is_discarded_like_system(service, extended, config):
    result = service.chat(
        _identity(service),
        {},
        _body(messages=[
            {"role": "developer", "content": "no reenviar"},
            {"role": "user", "content": "pregunta"},
        ]),
        time.monotonic(),
    )

    assert isinstance(result, CompletionResult)
    assert _audit(config)[-1]["discarded_system_messages"] == 1
    run_call = next(call for call in extended.calls if call[0] == "prompt.run")
    assert "no reenviar" not in json.dumps(run_call)


def test_text_content_parts_are_joined(service, extended):
    service.chat(
        _identity(service),
        {},
        _body(messages=[{"role": "user", "content": [
            {"type": "text", "text": "primera"},
            {"type": "text", "text": "segunda"},
        ]}]),
        time.monotonic(),
    )

    run_call = next(call for call in extended.calls if call[0] == "prompt.run")
    assert run_call[1]["prompt"] == "primera\nsegunda"


def test_unsupported_content_part_has_precise_field(service):
    with pytest.raises(RequestValidationError) as exc_info:
        service.chat(
            _identity(service),
            {},
            _body(messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "x"}},
            ]}]),
            time.monotonic(),
        )

    assert exc_info.value.field == "messages[0].content[0]"


def test_non_streaming_openai_shape_and_finish_mapping(service, extended):
    extended.run_response = {
        "output": "razonada",
        "trace": {"stop_reason": "max_iterations", "request_id": "r-1"},
    }
    result = service.chat(
        _identity(service), {}, _body(model="reasoned"), time.monotonic()
    )

    assert result.payload["object"] == "chat.completion"
    assert result.payload["choices"][0]["message"]["content"] == "razonada"
    assert result.payload["choices"][0]["finish_reason"] == "stop"


@pytest.mark.parametrize(
    ("raw", "translated"),
    [("stop", "stop"), ("length", "length"), ("incomplete", "length"), ("other", "stop")],
)
def test_finish_reason_translation(service, extended, raw, translated):
    extended.run_response = {
        "response": "r",
        "trace": {"finish_reason": raw, "request_id": "r-1"},
    }
    result = service.chat(_identity(service), {}, _body(), time.monotonic())
    assert result.payload["choices"][0]["finish_reason"] == translated


def test_stream_is_valid_openai_sse_and_ends_done(service):
    result = service.chat(
        _identity(service), {}, _body(stream=True), time.monotonic()
    )
    chunks = list(result.body)

    assert all(chunk.startswith(b"data: ") for chunk in chunks)
    assert b'"object":"chat.completion.chunk"' in chunks[0]
    assert b'"content":"res"' in chunks[0]
    assert b'"finish_reason":"stop"' in chunks[-2]
    assert chunks[-1] == b"data: [DONE]\n\n"


def test_midstream_downstream_error_is_emitted_as_sse_and_audited(
    service, extended, config
):
    expected = {
        "type": "CoreSpecificError",
        "message": "fallo durante flujo",
        "origin": "ia_nest_core",
    }
    extended.events = iter([
        SseEvent("token", {"data": {"text": "antes"}}),
        SseEvent("error", expected),
    ])

    result = service.chat(
        _identity(service), {}, _body(stream=True), time.monotonic()
    )
    chunks = list(result.body)

    assert json.loads(chunks[-1][len(b"data: ") :]) == {"error": expected}
    assert chunks[-1] != b"data: [DONE]\n\n"
    assert _audit(config)[-1]["outcome"] == "error"


def test_downstream_error_is_not_retyped(service, extended):
    expected = {
        "type": "CoreSpecificError",
        "message": "fallo",
        "origin": "ia_nest_core",
        "request_id": "core-7",
    }

    def fail(capability, payload):
        raise DownstreamError(expected, 409)

    extended.run = fail
    with pytest.raises(DownstreamError) as exc_info:
        service.chat(_identity(service), {}, _body(), time.monotonic())

    assert exc_info.value.error == expected
    assert exc_info.value.status_code == 409


def test_audit_never_contains_message_or_key(service, config):
    secret_message = "MESSAGE-MUST-NOT-LEAK"
    service.chat(
        _identity(service),
        {},
        _body(messages=[{"role": "user", "content": secret_message}]),
        time.monotonic(),
    )

    raw = config.audit_path.read_text(encoding="ascii")
    assert secret_message not in raw
    assert KEY not in raw

from __future__ import annotations

import json
import time

import pytest

from ianest_edge.client import SseEvent
from ianest_edge.errors import DownstreamError, RequestValidationError
from ianest_edge.service import CompletionResult, StreamingResult

from .conftest import BEARER


def _identity(service, person="adult@test"):
    return service.authenticate_and_resolve(BEARER, {"X-Person": person})


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


def test_models_contains_filtered_menu_plus_alias(service):
    payload = service.models(_identity(service), time.monotonic())
    assert [item["id"] for item in payload["data"]] == [
        "direct",
        "reasoned",
        "iterative",
        "ia_nest",
    ]


def test_valid_openai_request_forwards_directory_identity(service, extended):
    result = service.chat(
        _identity(service), {}, _body(model="direct"), time.monotonic()
    )
    assert isinstance(result, CompletionResult)
    call = next(item for item in extended.calls if item[0] == "prompt.run")
    assert call[1]["identity"]["user_id"] == "adult_user"
    assert call[1]["identity"]["service"] == "open_webui"
    assert call[1]["identity"]["interlocutor_profile"] == "adult"


def test_only_last_user_message_reaches_extended_and_system_is_audited(
    service, extended, config
):
    messages = [
        {"role": "system", "content": "secreto-sistema"},
        {"role": "user", "content": "primero"},
        {"role": "assistant", "content": "anterior"},
        {"role": "user", "content": "ultimo"},
    ]
    service.chat(
        _identity(service), {}, _body(messages=messages), time.monotonic()
    )
    run_call = next(call for call in extended.calls if call[0] == "prompt.run")
    assert run_call[1]["prompt"] == "ultimo"
    assert "secreto-sistema" not in json.dumps(run_call)
    assert _audit(config)[-1]["discarded_system_messages"] == 1


def test_fixed_and_auto_domain_translation(service, extended):
    identity = _identity(service)
    service.chat(identity, {}, _body(model="direct"), time.monotonic())
    service.chat(identity, {}, _body(model="reasoned"), time.monotonic())
    direct = next(call for call in extended.calls if call[0] == "prompt.run")
    reasoned = next(call for call in extended.calls if call[0] == "reasoning.run")
    assert direct[1]["domain"] == "linux"
    assert reasoned[1]["auto_domain"] is True


def test_iterative_prototype_runs_task(service, extended):
    result = service.chat(
        _identity(service), {}, _body(model="iterative"), time.monotonic()
    )
    assert isinstance(result, CompletionResult)
    assert any(call[0] == "task.run" for call in extended.calls)


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


def test_background_task_disables_write_back(service, extended, config):
    service.chat(
        _identity(service),
        {"X-Task": "title"},
        _body(),
        time.monotonic(),
    )
    call = next(item for item in extended.calls if item[0] == "prompt.run")
    assert call[1]["write_back"] is False
    assert _audit(config)[-1]["background_task"] is True


def test_stream_is_valid_openai_sse_and_ends_done(service):
    result = service.chat(
        _identity(service), {}, _body(stream=True), time.monotonic()
    )
    chunks = list(result.body)
    assert isinstance(result, StreamingResult)
    assert b'"content":"res"' in chunks[0]
    assert chunks[-1] == b"data: [DONE]\n\n"


def test_midstream_downstream_error_is_preserved(service, extended, config):
    expected = {
        "type": "CoreSpecificError",
        "message": "fallo durante flujo",
        "origin": "ia_nest_core",
    }
    extended.events = iter(
        [
            SseEvent("token", {"data": {"text": "antes"}}),
            SseEvent("error", expected),
        ]
    )
    chunks = list(
        service.chat(
            _identity(service), {}, _body(stream=True), time.monotonic()
        ).body
    )
    assert json.loads(chunks[-1][len(b"data: ") :]) == {"error": expected}
    assert _audit(config)[-1]["outcome"] == "error"


def test_non_stream_downstream_error_is_not_retyped(service, extended):
    expected = {
        "type": "CoreSpecificError",
        "message": "fallo",
        "origin": "ia_nest_core",
    }

    def fail(capability, payload):
        raise DownstreamError(expected, 409)

    extended.run = fail
    with pytest.raises(DownstreamError) as exc_info:
        service.chat(_identity(service), {}, _body(), time.monotonic())
    assert exc_info.value.error == expected


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
    assert BEARER not in raw
    assert _audit(config)[-1]["face"] == "openai"

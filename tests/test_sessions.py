from __future__ import annotations

import time

from ianest_edge.errors import DownstreamError

from .conftest import KEY
from .test_service import _body


def _identity(service):
    return service.authenticate_and_resolve(
        f"Bearer {KEY}", {"X-Person": "adult"}
    )


def _run(service, headers, messages=None):
    return service.chat(
        _identity(service),
        headers,
        _body(messages=messages),
        time.monotonic(),
    )


def _session_for_call(extended, index=-1):
    calls = [call for call in extended.calls if call[0] == "prompt.run"]
    return calls[index][1]["identity"]["session_id"]


def test_different_chats_do_not_share_and_same_chat_continues(service, extended):
    _run(service, {"X-Chat": "one"})
    first = _session_for_call(extended)
    _run(service, {"X-Chat": "two"})
    second = _session_for_call(extended)
    _run(service, {"X-Chat": "one"})
    repeated = _session_for_call(extended)

    assert first == "chat-one-1"
    assert second == "chat-two-1"
    assert repeated == first


def test_archived_chat_creates_next_suffix(service, extended):
    extended.sessions = [
        {
            "session_id": "chat-one-1",
            "status": "archivada",
            "last_activity_at": "2026-10-21T00:00:00+00:00",
        }
    ]

    _run(service, {"X-Chat": "one"})

    assert _session_for_call(extended) == "chat-one-2"


def test_duplicate_chat_session_creation_uses_winning_active_session(
    service, extended
):
    original_new = extended.session_new

    def duplicate_then_publish(identity, session_id=None):
        if session_id == "chat-one-1":
            extended.sessions.append({
                "session_id": session_id,
                "status": "activa",
                "last_activity_at": "2026-10-22T00:00:00+00:00",
            })
            raise DownstreamError(
                {
                    "type": "SessionAlreadyExistsError",
                    "message": "duplicada",
                    "origin": "ia_nest_extended",
                },
                409,
            )
        return original_new(identity, session_id)

    extended.session_new = duplicate_then_publish
    _run(service, {"X-Chat": "one"})

    assert _session_for_call(extended) == "chat-one-1"


def test_without_chat_one_user_message_always_creates(service, extended):
    _run(service, {})
    _run(service, {})
    assert [_session_for_call(extended, 0), _session_for_call(extended, 1)] == [
        "generated-1",
        "generated-2",
    ]


def test_without_chat_history_uses_most_recent_active(service, extended):
    extended.sessions = [
        {
            "session_id": "old",
            "status": "activa",
            "last_activity_at": "2026-10-20T00:00:00+00:00",
        },
        {
            "session_id": "new",
            "status": "activa",
            "last_activity_at": "2026-10-22T00:00:00+00:00",
        },
    ]
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "second"},
    ]

    _run(service, {}, messages)

    assert _session_for_call(extended) == "new"

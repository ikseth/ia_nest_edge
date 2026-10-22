from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ianest_edge.audit import AuditWriter
from ianest_edge.client import SseEvent
from ianest_edge.config import EdgeConfig
from ianest_edge.service import EdgeService
from ianest_edge.identity import FileIdentityResolver


KEY = "a-long-random-test-key"
KEY_HASH = hashlib.sha256(KEY.encode("utf-8")).hexdigest()


def config_dict(tmp_path: Path):
    child_menu = [
        {
            "id": "child_direct",
            "mode": "directo",
            "domain": "auto",
            "default": True,
        }
    ]
    adult_menu = [
        {
            "id": "direct",
            "mode": "directo",
            "domain": "linux",
            "default": True,
        },
        {
            "id": "reasoned",
            "mode": "razonado",
            "domain": "auto",
            "default": False,
        },
        {
            "id": "iterative",
            "mode": "iterativo",
            "domain": "auto",
            "default": False,
        },
    ]
    return {
        "server": {"host": "127.0.0.1", "port": 8080},
        "extended": {"base_url": "http://127.0.0.1:8001"},
        "audit": {"path": str(tmp_path / "edge.jsonl")},
        "guest": {
            "user_id": "guest",
            "profile": "child",
            "menu": child_menu,
        },
        "consumers": {
            "chat": {
                "key_sha256": KEY_HASH,
                "can_assert_people": True,
                "headers": {
                    "chat": "X-Chat",
                    "person": "X-Person",
                    "background_task": "X-Task",
                },
                "default_identity": {
                    "user_id": "shared",
                    "profile": "adult",
                    "menu": adult_menu,
                },
                "people": {
                    "adult": {
                        "user_id": "adult-user",
                        "profile": "adult",
                        "menu": adult_menu,
                    },
                    "child": {
                        "user_id": "child-user",
                        "profile": "child",
                        "menu": child_menu,
                    },
                    "unknown_profile": {
                        "user_id": "unknown-user",
                        "profile": "unexpected",
                        "menu": child_menu,
                    },
                },
            }
        },
    }


class FakeExtended:
    def __init__(self):
        self.calls = []
        self.sessions = []
        self.generated = 0
        self.run_response = {
            "response": "respuesta",
            "trace": {"finish_reason": "stop", "request_id": "extended-1"},
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 1,
                "total_tokens": 3,
            },
        }
        self.events = [
            SseEvent("token", {"type": "token", "data": {"text": "res"}}),
            SseEvent(
                "token", {"type": "token", "data": {"text": "puesta"}}
            ),
            SseEvent(
                "done",
                {
                    "type": "done",
                    "data": {"finish_reason": "stop", "response": "respuesta"},
                },
            ),
        ]

    def domain_list(self):
        self.calls.append(("domain.list", None))
        return {"domains": [{"id": "general"}, {"id": "linux"}]}

    def session_list(self, identity, status):
        self.calls.append(("session.list", identity, status))
        selected = self.sessions
        if status != "todas":
            selected = [item for item in selected if item["status"] == status]
        return {"sessions": [dict(item) for item in selected]}

    def session_new(self, identity, session_id=None):
        self.calls.append(("session.new", identity, session_id))
        if session_id is None:
            self.generated += 1
            session_id = f"generated-{self.generated}"
        session = {
            "session_id": session_id,
            "status": "activa",
            "last_activity_at": f"2026-10-22T00:00:0{len(self.sessions)}+00:00",
        }
        self.sessions.append(session)
        return {"session": dict(session)}

    def run(self, capability, payload):
        self.calls.append((capability, payload))
        return dict(self.run_response)

    def stream(self, capability, payload):
        self.calls.append((capability, payload))
        return iter(self.events)


@pytest.fixture
def config(tmp_path):
    return EdgeConfig.from_dict(config_dict(tmp_path))


@pytest.fixture
def extended():
    return FakeExtended()


@pytest.fixture
def service(config, extended):
    return EdgeService(
        config,
        resolver=FileIdentityResolver(config),
        client=extended,
        audit=AuditWriter(config.audit_path),
    )

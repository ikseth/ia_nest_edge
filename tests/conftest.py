from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ianest_edge.audit import AuditWriter
from ianest_edge.client import ForwardedJson, ForwardedStream, SseEvent
from ianest_edge.config import EdgeConfig
from ianest_edge.identity import DirectoryEntry, DirectoryIdentityResolver
from ianest_edge.service import EdgeService


UID = "chat_service"
KEY = "a-long-random-test-key"
BEARER = f"Bearer {UID}.{KEY}"
KEY_HASH = hashlib.sha256(KEY.encode("utf-8")).hexdigest()


def config_dict(tmp_path: Path):
    ca_file = tmp_path / "directory-ca.pem"
    password_file = tmp_path / "directory-password"
    ca_file.touch(exist_ok=True)
    password_file.write_text("bind-password\n", encoding="ascii")
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
        },
        {
            "id": "iterative",
            "mode": "iterativo",
            "domain": "auto",
            "prototype": True,
        },
    ]
    return {
        "server": {"host": "127.0.0.1", "port": 8080},
        "extended": {"base_url": "http://127.0.0.1:8001"},
        "audit": {"path": str(tmp_path / "edge.jsonl")},
        "directory": {
            "url": "ldaps://directory.test:636",
            "base_dn": "dc=example,dc=test",
            "people_dn": "ou=people,dc=example,dc=test",
            "ca_file": str(ca_file),
            "bind_dn": "uid=edge,ou=services,dc=example,dc=test",
            "bind_password_file": str(password_file),
        },
        "classes": {
            "open_webui": {
                "headers": {
                    "chat": "X-Chat",
                    "person": "X-Person",
                    "background_task": "X-Task",
                },
                "menus": {"adult": adult_menu, "child": child_menu},
            },
            "api": {
                "headers": {},
                "menus": {"adult": adult_menu, "child": child_menu},
            },
        },
        "api": {
            "allowed_capabilities": [
                "capability.list",
                "prompt.run",
                "prompt.stream",
                "session.list",
                "runtime.health",
            ]
        },
    }


class FakeDirectory:
    def __init__(self):
        service_groups = frozenset(
            {
                "ia_nest_services",
                "edge_class_open_webui",
                "edge_asserts_people",
            }
        )
        self.entries = [
            DirectoryEntry(UID, "service@test", service_groups, KEY_HASH),
            DirectoryEntry(
                "api_service",
                "api@test",
                frozenset(
                    {
                        "ia_nest_services",
                        "edge_class_api",
                        "profile_adult",
                        "edge_prototypes",
                    }
                ),
                KEY_HASH,
            ),
            DirectoryEntry(
                "adult_user",
                "adult@test",
                frozenset(
                    {"ia_nest_users", "profile_adult", "edge_prototypes"}
                ),
            ),
            DirectoryEntry(
                "child_user",
                "child@test",
                frozenset({"ia_nest_users", "profile_child"}),
            ),
            DirectoryEntry(
                "both_user",
                "both@test",
                frozenset(
                    {"ia_nest_users", "profile_adult", "profile_child"}
                ),
            ),
            DirectoryEntry(
                "unknown_user", "unknown@test", frozenset({"ia_nest_users"})
            ),
            DirectoryEntry(
                "outside_user", "outside@test", frozenset({"profile_adult"})
            ),
        ]
        self.calls = []
        self.unavailable = False

    def find(self, attribute, value, *, key_attribute):
        from ianest_edge.errors import DirectoryUnavailableError

        self.calls.append((attribute, value, key_attribute))
        if self.unavailable:
            raise DirectoryUnavailableError("directorio falso caido")
        return [
            item
            for item in self.entries
            if getattr(item, attribute, None) == value
        ]


def _capability(
    name, *, method="POST", streaming=False, mcp=True, params=None
):
    return {
        "name": name,
        "summary": f"Resumen de {name}",
        "streaming": streaming,
        "params": params or [],
        "rest": {"method": method, "path": "/" + name.replace(".", "/")},
        "mcp": {"tool": name} if mcp else None,
    }


class FakeExtended:
    def __init__(self):
        self.calls = []
        self.sessions = []
        self.generated = 0
        self.run_response = {
            "response": "respuesta",
            "trace": {"finish_reason": "stop", "request_id": "extended-1"},
        }
        self.events = [
            SseEvent("token", {"type": "token", "data": {"text": "res"}}),
            SseEvent("token", {"type": "token", "data": {"text": "puesta"}}),
            SseEvent(
                "done",
                {"type": "done", "data": {"finish_reason": "stop"}},
            ),
        ]
        self.capabilities = [
            _capability("capability.list", method="GET"),
            _capability(
                "prompt.run",
                params=[
                    {
                        "name": "prompt",
                        "type": "string",
                        "required": True,
                        "summary": "texto",
                    }
                ],
            ),
            _capability("prompt.stream", streaming=True, mcp=False),
            _capability("session.list"),
            _capability("runtime.health", method="GET"),
            _capability("not.allowed"),
        ]

    def domain_list(self):
        self.calls.append(("domain.list", None))
        return {"domains": [{"id": "general"}, {"id": "linux"}]}

    def capability_list(self):
        self.calls.append(("capability.list", None))
        return {"capabilities": [dict(item) for item in self.capabilities]}

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
            "last_activity_at": "2026-10-22T00:00:00+00:00",
        }
        self.sessions.append(session)
        return {"session": dict(session)}

    def run(self, capability, payload):
        self.calls.append((capability, payload))
        return dict(self.run_response)

    def stream(self, capability, payload):
        self.calls.append((capability, payload))
        return iter(self.events)

    def forward(
        self,
        method,
        route,
        *,
        query="",
        payload,
    ):
        self.calls.append(("forward", method, route, query, payload))
        if route == "/prompt/stream":
            return ForwardedStream(
                iter((b"event: token\ndata: one\n\n", b"event: done\ndata: {}\n\n")),
                200,
                "text/event-stream",
            )
        return ForwardedJson(
            {"ok": True, "received_identity": (payload or {}).get("identity")},
            200,
            "application/json",
        )


@pytest.fixture
def config(tmp_path):
    return EdgeConfig.from_dict(config_dict(tmp_path))


@pytest.fixture
def directory():
    return FakeDirectory()


@pytest.fixture
def extended():
    return FakeExtended()


@pytest.fixture
def service(config, directory, extended):
    return EdgeService(
        config,
        resolver=DirectoryIdentityResolver(config, directory),
        client=extended,
        audit=AuditWriter(config.audit_path),
    )

"""Auditoria JSONL sin contenido conversacional ni credenciales."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AuditRecord:
    face: str
    consumer: str | None
    user_id: str | None
    interlocutor_profile: str | None
    menu_entry: str | None
    mode: str | None
    capability: str | None
    session_id: str | None
    background_task: bool
    discarded_system_messages: int
    outcome: str
    finish_reason: str | None
    identity_overridden: bool
    latency_ms: int
    timestamp: str = ""


class AuditWriter:
    def __init__(self, path: Path) -> None:
        self._path = path

    def write(self, record: AuditRecord) -> None:
        payload = asdict(record)
        if not payload["timestamp"]:
            payload["timestamp"] = datetime.now(UTC).isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        with self._path.open("a", encoding="ascii") as stream:
            stream.write(line + "\n")

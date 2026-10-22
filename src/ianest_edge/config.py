"""Carga y validacion estructural de la configuracion YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigurationError

CONFIG_ENV = "IANEST_EDGE_CONFIG"
DEFAULT_CONFIG_PATH = "config/edge.yaml"
PROFILE_ADULT = "adult"
PROFILE_CHILD = "child"
VALID_MODES = frozenset({"directo", "razonado", "iterativo"})


@dataclass(frozen=True, slots=True)
class MenuEntry:
    id: str
    mode: str
    domain: str
    default: bool = False


@dataclass(frozen=True, slots=True)
class IdentityConfig:
    user_id: str
    profile: str
    menu: tuple[MenuEntry, ...]

    @property
    def default_entry(self) -> MenuEntry:
        return next(item for item in self.menu if item.default)


@dataclass(frozen=True, slots=True)
class HeaderConfig:
    chat: str | None = None
    person: str | None = None
    background_task: str | None = None


@dataclass(frozen=True, slots=True)
class ConsumerConfig:
    name: str
    key_sha256: str
    can_assert_people: bool
    headers: HeaderConfig
    default_identity: IdentityConfig
    people: dict[str, IdentityConfig]


@dataclass(frozen=True, slots=True)
class EdgeConfig:
    extended_url: str
    audit_path: Path
    host: str
    port: int
    consumers: tuple[ConsumerConfig, ...]
    guest: IdentityConfig
    connect_timeout_seconds: float = 30.0
    inactivity_timeout_seconds: float = 600.0

    @classmethod
    def from_env(cls) -> "EdgeConfig":
        return cls.from_path(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG_PATH))

    @classmethod
    def from_path(cls, path: str | Path) -> "EdgeConfig":
        config_path = Path(path)
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigurationError(
                f"no se pudo leer la configuracion {config_path}: {exc}",
                CONFIG_ENV,
            ) from exc
        except yaml.YAMLError as exc:
            raise ConfigurationError(
                f"la configuracion YAML no es valida: {exc}",
                str(config_path),
            ) from exc
        if not isinstance(raw, dict):
            raise ConfigurationError("la configuracion debe ser un objeto", "config")
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EdgeConfig":
        server = _mapping(raw.get("server", {}), "server")
        extended = _mapping(raw.get("extended", {}), "extended")
        audit = _mapping(raw.get("audit", {}), "audit")
        guest = _identity(
            _mapping(raw.get("guest"), "guest"),
            "guest",
            force_child=True,
        )
        consumers_raw = raw.get("consumers")
        consumers = _consumers(consumers_raw)
        if not consumers:
            raise ConfigurationError(
                "debe declararse al menos un consumidor", "consumers"
            )
        hashes = [item.key_sha256 for item in consumers]
        if len(set(hashes)) != len(hashes):
            raise ConfigurationError(
                "dos consumidores no pueden compartir key_sha256",
                "consumers.key_sha256",
            )
        host = _text(server.get("host", "127.0.0.1"), "server.host")
        port = _integer(server.get("port", 8080), "server.port")
        if not 1 <= port <= 65535:
            raise ConfigurationError(
                "server.port debe estar entre 1 y 65535", "server.port"
            )
        return cls(
            extended_url=_text(extended.get("base_url"), "extended.base_url").rstrip("/"),
            audit_path=Path(_text(audit.get("path"), "audit.path")),
            host=host,
            port=port,
            consumers=tuple(consumers),
            guest=guest,
            connect_timeout_seconds=_positive_number(
                extended.get("connect_timeout_seconds", 30.0),
                "extended.connect_timeout_seconds",
            ),
            inactivity_timeout_seconds=_positive_number(
                extended.get("inactivity_timeout_seconds", 600.0),
                "extended.inactivity_timeout_seconds",
            ),
        )


def _consumers(raw: Any) -> list[ConsumerConfig]:
    if isinstance(raw, dict):
        values = []
        for name, body in raw.items():
            item = dict(_mapping(body, f"consumers.{name}"))
            item.setdefault("name", name)
            values.append(item)
    elif isinstance(raw, list):
        values = raw
    else:
        raise ConfigurationError(
            "consumers debe ser una lista o un objeto", "consumers"
        )
    result = []
    names: set[str] = set()
    for index, raw_consumer in enumerate(values):
        field = f"consumers[{index}]"
        body = _mapping(raw_consumer, field)
        name = _text(body.get("name"), f"{field}.name")
        if name in names:
            raise ConfigurationError(
                f"el consumidor {name!r} esta repetido", f"{field}.name"
            )
        names.add(name)
        digest = _text(body.get("key_sha256"), f"{field}.key_sha256").lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ConfigurationError(
                "key_sha256 debe contener 64 caracteres hexadecimales",
                f"{field}.key_sha256",
            )
        headers_raw = _mapping(body.get("headers", {}), f"{field}.headers")
        default_raw = body.get("default_identity", body.get("identity"))
        default_identity = _identity(
            _mapping(default_raw, f"{field}.default_identity"),
            f"{field}.default_identity",
        )
        people_raw = _mapping(body.get("people", {}), f"{field}.people")
        people = {
            _text(person_key, f"{field}.people.key"): _identity(
                _mapping(person, f"{field}.people.{person_key}"),
                f"{field}.people.{person_key}",
            )
            for person_key, person in people_raw.items()
        }
        result.append(
            ConsumerConfig(
                name=name,
                key_sha256=digest,
                can_assert_people=_boolean(
                    body.get("can_assert_people", False),
                    f"{field}.can_assert_people",
                ),
                headers=HeaderConfig(
                    chat=_optional_text(headers_raw.get("chat"), f"{field}.headers.chat"),
                    person=_optional_text(
                        headers_raw.get("person"), f"{field}.headers.person"
                    ),
                    background_task=_optional_text(
                        headers_raw.get("background_task"),
                        f"{field}.headers.background_task",
                    ),
                ),
                default_identity=default_identity,
                people=people,
            )
        )
    return result


def _identity(
    raw: dict[str, Any],
    field: str,
    *,
    force_child: bool = False,
) -> IdentityConfig:
    menu_raw = raw.get("menu")
    if not isinstance(menu_raw, list) or not menu_raw:
        raise ConfigurationError("menu debe ser una lista no vacia", f"{field}.menu")
    menu = tuple(
        _menu_entry(_mapping(item, f"{field}.menu[{index}]"), f"{field}.menu[{index}]")
        for index, item in enumerate(menu_raw)
    )
    ids = [item.id for item in menu]
    if len(set(ids)) != len(ids):
        raise ConfigurationError("los id del menu deben ser unicos", f"{field}.menu")
    if "ia_nest" in ids:
        raise ConfigurationError(
            "ia_nest esta reservado para la entrada por defecto", f"{field}.menu"
        )
    if sum(item.default for item in menu) != 1:
        raise ConfigurationError(
            "el menu debe tener exactamente una entrada default",
            f"{field}.menu",
        )
    return IdentityConfig(
        user_id=_text(raw.get("user_id"), f"{field}.user_id"),
        profile=PROFILE_CHILD if force_child else _profile(raw.get("profile")),
        menu=menu,
    )


def _menu_entry(raw: dict[str, Any], field: str) -> MenuEntry:
    mode = _text(raw.get("mode"), f"{field}.mode")
    if mode not in VALID_MODES:
        raise ConfigurationError(
            f"mode debe ser uno de {sorted(VALID_MODES)}", f"{field}.mode"
        )
    domain = _text(raw.get("domain"), f"{field}.domain")
    default = _boolean(raw.get("default", False), f"{field}.default")
    return MenuEntry(
        id=_text(raw.get("id"), f"{field}.id"),
        mode=mode,
        domain=domain,
        default=default,
    )


def _profile(value: Any) -> str:
    return value if value in {PROFILE_ADULT, PROFILE_CHILD} else PROFILE_CHILD


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{field} debe ser un objeto", field)
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field} debe ser texto no vacio", field)
    return value.strip()


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationError(f"{field} debe ser booleano", field)
    return value


def _integer(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"{field} debe ser entero", field)
    return value


def _positive_number(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ConfigurationError(f"{field} debe ser mayor que cero", field)
    return float(value)

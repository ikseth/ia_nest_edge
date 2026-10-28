"""Carga y validacion estructural de la configuracion YAML."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from .errors import ConfigurationError

CONFIG_ENV = "IANEST_EDGE_CONFIG"
DEFAULT_CONFIG_PATH = "config/edge.yaml"
PROFILE_ADULT = "adult"
PROFILE_CHILD = "child"
VALID_MODES = frozenset({"directo", "razonado", "iterativo"})
FORBIDDEN_LEGACY_KEYS = frozenset({"consumers", "people", "key_sha256", "guest"})
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class MenuEntry:
    id: str
    mode: str
    domain: str
    default: bool = False
    prototype: bool = False


@dataclass(frozen=True, slots=True)
class HeaderConfig:
    chat: str | None = None
    person: str | None = None
    background_task: str | None = None


@dataclass(frozen=True, slots=True)
class TlsConfig:
    certfile: Path
    keyfile: Path


@dataclass(frozen=True, slots=True)
class ClassConfig:
    name: str
    write_memory: bool
    headers: HeaderConfig
    menus: dict[str, tuple[MenuEntry, ...]]

    def menu_for(self, profile: str, *, prototypes: bool) -> tuple[MenuEntry, ...]:
        return tuple(
            entry
            for entry in self.menus[profile]
            if prototypes or not entry.prototype
        )


@dataclass(frozen=True, slots=True)
class DirectoryGroups:
    users: str = "ia_nest_users"
    services: str = "ia_nest_services"
    adult: str = "profile_adult"
    child: str = "profile_child"
    asserts_people: str = "edge_asserts_people"
    prototypes: str = "edge_prototypes"
    class_prefix: str = "edge_class_"


@dataclass(frozen=True, slots=True)
class DirectoryConfig:
    url: str
    base_dn: str
    people_dn: str
    ca_file: Path
    bind_dn: str
    bind_password_file: Path
    timeout_seconds: float
    key_attribute: str
    groups: DirectoryGroups


@dataclass(frozen=True, slots=True)
class EdgeConfig:
    extended_url: str
    audit_path: Path
    host: str
    port: int
    tls: TlsConfig | None
    directory: DirectoryConfig
    classes: dict[str, ClassConfig]
    allowed_capabilities: tuple[str, ...]
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
        legacy = _find_legacy_key(raw)
        if legacy is not None:
            raise ConfigurationError(
                f"la clave de la primera entrega '{legacy[1]}' ya no esta permitida",
                legacy[0],
            )
        server = _mapping(raw.get("server", {}), "server")
        extended = _mapping(raw.get("extended", {}), "extended")
        audit = _mapping(raw.get("audit", {}), "audit")
        host = _text(server.get("host", "127.0.0.1"), "server.host")
        port = _integer(server.get("port", 8080), "server.port")
        if not 1 <= port <= 65535:
            raise ConfigurationError(
                "server.port debe estar entre 1 y 65535", "server.port"
            )
        classes = _classes(raw.get("classes"))
        api = _mapping(raw.get("api"), "api")
        capabilities = _text_list(
            api.get("allowed_capabilities"), "api.allowed_capabilities"
        )
        if len(set(capabilities)) != len(capabilities):
            raise ConfigurationError(
                "allowed_capabilities no admite nombres repetidos",
                "api.allowed_capabilities",
            )
        return cls(
            extended_url=_text(
                extended.get("base_url"), "extended.base_url"
            ).rstrip("/"),
            audit_path=Path(_text(audit.get("path"), "audit.path")),
            host=host,
            port=port,
            tls=_tls(server.get("tls")),
            directory=_directory(raw.get("directory")),
            classes=classes,
            allowed_capabilities=tuple(capabilities),
            connect_timeout_seconds=_positive_number(
                extended.get("connect_timeout_seconds", 30.0),
                "extended.connect_timeout_seconds",
            ),
            inactivity_timeout_seconds=_positive_number(
                extended.get("inactivity_timeout_seconds", 600.0),
                "extended.inactivity_timeout_seconds",
            ),
        )


def _find_legacy_key(value: Any, path: str = "config") -> tuple[str, str] | None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_LEGACY_KEYS:
                return child_path, key
            found = _find_legacy_key(child, child_path)
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_legacy_key(child, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _directory(raw: Any) -> DirectoryConfig:
    body = _mapping(raw, "directory")
    url = _text(body.get("url"), "directory.url")
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError as exc:
        raise ConfigurationError(
            "directory.url contiene un puerto no valido", "directory.url"
        ) from exc
    if (
        parts.scheme != "ldaps"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ConfigurationError(
            "directory.url debe ser una URL ldaps sin credenciales, ruta ni query",
            "directory.url",
        )
    ca_file = _required_file(body.get("ca_file"), "directory.ca_file")
    password_file = _required_file(
        body.get("bind_password_file"), "directory.bind_password_file"
    )
    groups_raw = _mapping(body.get("groups", {}), "directory.groups")
    defaults = DirectoryGroups()
    groups = DirectoryGroups(
        users=_text(groups_raw.get("users", defaults.users), "directory.groups.users"),
        services=_text(
            groups_raw.get("services", defaults.services),
            "directory.groups.services",
        ),
        adult=_text(groups_raw.get("adult", defaults.adult), "directory.groups.adult"),
        child=_text(groups_raw.get("child", defaults.child), "directory.groups.child"),
        asserts_people=_text(
            groups_raw.get("asserts_people", defaults.asserts_people),
            "directory.groups.asserts_people",
        ),
        prototypes=_text(
            groups_raw.get("prototypes", defaults.prototypes),
            "directory.groups.prototypes",
        ),
        class_prefix=_text(
            groups_raw.get("class_prefix", defaults.class_prefix),
            "directory.groups.class_prefix",
        ),
    )
    return DirectoryConfig(
        url=url,
        base_dn=_text(body.get("base_dn"), "directory.base_dn"),
        people_dn=_text(body.get("people_dn"), "directory.people_dn"),
        ca_file=ca_file,
        bind_dn=_text(body.get("bind_dn"), "directory.bind_dn"),
        bind_password_file=password_file,
        timeout_seconds=_positive_number(
            body.get("timeout_seconds", 3), "directory.timeout_seconds"
        ),
        key_attribute=_text(
            body.get("key_attribute", "edge-key-sha256"),
            "directory.key_attribute",
        ),
        groups=groups,
    )


def _classes(raw: Any) -> dict[str, ClassConfig]:
    body = _mapping(raw, "classes")
    if not body:
        raise ConfigurationError("debe declararse al menos una clase", "classes")
    result: dict[str, ClassConfig] = {}
    for raw_name, raw_class in body.items():
        name = _text(raw_name, "classes.key")
        if not IDENTIFIER_PATTERN.fullmatch(name):
            raise ConfigurationError(
                "el nombre de clase debe ser un identificador snake_case",
                f"classes.{name}",
            )
        field = f"classes.{name}"
        class_body = _mapping(raw_class, field)
        headers_raw = _mapping(class_body.get("headers", {}), f"{field}.headers")
        menus_raw = _mapping(class_body.get("menus"), f"{field}.menus")
        menus = {
            profile: _menu(menus_raw.get(profile), f"{field}.menus.{profile}")
            for profile in (PROFILE_ADULT, PROFILE_CHILD)
        }
        result[name] = ClassConfig(
            name=name,
            write_memory=_boolean(
                class_body.get("write_memory", True), f"{field}.write_memory"
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
            menus=menus,
        )
    return result


def _menu(raw: Any, field: str) -> tuple[MenuEntry, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigurationError("menu debe ser una lista no vacia", field)
    menu = tuple(
        _menu_entry(_mapping(item, f"{field}[{index}]"), f"{field}[{index}]")
        for index, item in enumerate(raw)
    )
    ids = [item.id for item in menu]
    if len(set(ids)) != len(ids):
        raise ConfigurationError("los id del menu deben ser unicos", field)
    if "ia_nest" in ids:
        raise ConfigurationError(
            "ia_nest esta reservado para la entrada por defecto", field
        )
    stable = tuple(item for item in menu if not item.prototype)
    if sum(item.default for item in stable) != 1:
        raise ConfigurationError(
            "el menu sin prototipos debe tener exactamente una entrada default",
            field,
        )
    if sum(item.default for item in menu) != 1:
        raise ConfigurationError(
            "una entrada prototype no puede anadir otro default", field
        )
    return menu


def _menu_entry(raw: dict[str, Any], field: str) -> MenuEntry:
    mode = _text(raw.get("mode"), f"{field}.mode")
    if mode not in VALID_MODES:
        raise ConfigurationError(
            f"mode debe ser uno de {sorted(VALID_MODES)}", f"{field}.mode"
        )
    return MenuEntry(
        id=_text(raw.get("id"), f"{field}.id"),
        mode=mode,
        domain=_text(raw.get("domain"), f"{field}.domain"),
        default=_boolean(raw.get("default", False), f"{field}.default"),
        prototype=_boolean(raw.get("prototype", False), f"{field}.prototype"),
    )


def _tls(raw: Any) -> TlsConfig | None:
    if raw is None:
        return None
    tls = _mapping(raw, "server.tls")
    certfile = _optional_text(tls.get("certfile"), "server.tls.certfile")
    keyfile = _optional_text(tls.get("keyfile"), "server.tls.keyfile")
    if (certfile is None) != (keyfile is None):
        raise ConfigurationError(
            "server.tls requiere certfile y keyfile juntos", "server.tls"
        )
    if certfile is None:
        return None
    return TlsConfig(
        certfile=_required_file(certfile, "server.tls.certfile"),
        keyfile=_required_file(keyfile, "server.tls.keyfile"),
    )


def _required_file(value: Any, field: str) -> Path:
    path = Path(_text(value, field))
    if not path.is_file():
        raise ConfigurationError(f"el fichero no existe: {path}", field)
    return path


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


def _text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{field} debe ser una lista no vacia", field)
    return [_text(item, f"{field}[{index}]") for index, item in enumerate(value)]


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

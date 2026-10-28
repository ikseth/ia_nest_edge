"""Punto unico de autenticacion y resolucion de identidades."""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import ssl
import threading
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

from .config import ClassConfig, DirectoryConfig, EdgeConfig, MenuEntry
from .errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DirectoryUnavailableError,
)

UID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


@dataclass(frozen=True, slots=True)
class DirectoryEntry:
    uid: str | None
    mail: str | None
    groups: frozenset[str]
    key_sha256: str | None = None


class DirectoryClient(Protocol):
    def find(
        self,
        attribute: str,
        value: str,
        *,
        key_attribute: str,
    ) -> list[DirectoryEntry]: ...


@dataclass(frozen=True, slots=True)
class AuthenticatedAccount:
    uid: str
    groups: frozenset[str]
    consumer_class: ClassConfig


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    consumer: str
    consumer_class: ClassConfig
    user_id: str
    service: str
    interlocutor_profile: str
    menu: tuple[MenuEntry, ...]

    @property
    def default_entry(self) -> MenuEntry:
        return next(item for item in self.menu if item.default)


class IdentityResolver(Protocol):
    def authenticate(self, authorization: str | None) -> AuthenticatedAccount: ...

    def resolve(
        self,
        consumer: AuthenticatedAccount,
        headers: Mapping[str, str],
    ) -> ResolvedIdentity: ...


class LdapDirectoryClient:
    """Consultas LDAPS verificadas, sin cache de entradas."""

    def __init__(self, config: DirectoryConfig) -> None:
        self._config = config
        self._connection: Any | None = None
        self._lock = threading.Lock()
        try:
            self._password = config.bind_password_file.read_text(
                encoding="utf-8"
            ).rstrip("\r\n")
        except OSError as exc:
            raise ConfigurationError(
                f"no se pudo leer bind_password_file: {exc}",
                "directory.bind_password_file",
            ) from exc
        if not self._password:
            raise ConfigurationError(
                "bind_password_file no puede estar vacio",
                "directory.bind_password_file",
            )

    def find(
        self,
        attribute: str,
        value: str,
        *,
        key_attribute: str,
    ) -> list[DirectoryEntry]:
        try:
            from ldap3 import NONE, SUBTREE, Connection, Server, Tls
            from ldap3.core.exceptions import LDAPException
            from ldap3.utils.conv import escape_filter_chars
        except ImportError as exc:  # pragma: no cover - dependencia obligatoria
            raise RuntimeError("ldap3 no esta instalado") from exc

        with self._lock:
            for attempt in range(2):
                try:
                    connection = self._connection or self._open_connection(
                        Connection, Server, Tls, NONE
                    )
                    self._connection = connection
                    escaped = escape_filter_chars(value)
                    connection.search(
                        self._config.people_dn,
                        f"({attribute}={escaped})",
                        search_scope=SUBTREE,
                        attributes=["uid", "mail", "memberOf", key_attribute],
                        time_limit=self._ldap_timeout_seconds(),
                    )
                    return [
                        _ldap_entry(item.entry_attributes_as_dict, key_attribute)
                        for item in connection.entries
                    ]
                except DirectoryUnavailableError:
                    raise
                except Exception as exc:
                    self._discard_connection(LDAPException)
                    if attempt == 0:
                        continue
                    raise DirectoryUnavailableError(
                        f"el directorio no esta disponible: {exc}"
                    ) from exc

        raise AssertionError("el reintento del directorio no devolvio resultado")

    def _open_connection(self, connection_type, server_type, tls_type, none):
        parts = urlsplit(self._config.url)
        tls = tls_type(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=str(self._config.ca_file),
        )
        server = server_type(
            parts.hostname,
            port=parts.port or 636,
            use_ssl=True,
            tls=tls,
            get_info=none,
            connect_timeout=self._config.timeout_seconds,
        )
        connection = connection_type(
            server,
            user=self._config.bind_dn,
            password=self._password,
            receive_timeout=self._ldap_timeout_seconds(),
            raise_exceptions=True,
        )
        if not connection.bind():
            raise OSError("el bind del directorio fallo")
        return connection

    def _ldap_timeout_seconds(self) -> int:
        return max(1, math.ceil(self._config.timeout_seconds))

    def _discard_connection(self, ldap_exception) -> None:
        connection = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            connection.unbind()
        except Exception:
            pass


class DirectoryIdentityResolver:
    """Resuelve cada peticion contra el directorio, sin cache de identidad."""

    def __init__(
        self,
        config: EdgeConfig,
        directory: DirectoryClient | None = None,
    ) -> None:
        self._config = config
        self._directory = directory or LdapDirectoryClient(config.directory)

    def authenticate(self, authorization: str | None) -> AuthenticatedAccount:
        uid, secret = _bearer_parts(authorization)
        entries = self._directory.find(
            "uid",
            uid,
            key_attribute=self._config.directory.key_attribute,
        )
        if len(entries) != 1:
            raise AuthenticationError("la cuenta no existe", "Authorization")
        account = entries[0]
        groups = self._config.directory.groups
        if groups.services not in account.groups:
            raise AuthenticationError(
                "la cuenta no pertenece al grupo de servicios", "Authorization"
            )
        if not account.key_sha256:
            raise AuthenticationError(
                "la cuenta no tiene clave del borde", "Authorization"
            )
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(digest, account.key_sha256.lower()):
            raise AuthenticationError("la clave Bearer no es valida", "Authorization")
        class_names = sorted(
            name
            for name in self._config.classes
            if f"{groups.class_prefix}{name}" in account.groups
        )
        declared_group_names = {
            value[len(groups.class_prefix) :]
            for value in account.groups
            if value.startswith(groups.class_prefix)
        }
        if len(declared_group_names) != 1 or len(class_names) != 1:
            raise AuthorizationError(
                "la cuenta debe pertenecer a una unica clase declarada"
            )
        class_name = class_names[0]
        return AuthenticatedAccount(
            uid=uid,
            groups=account.groups,
            consumer_class=self._config.classes[class_name],
        )

    def resolve(
        self,
        consumer: AuthenticatedAccount,
        headers: Mapping[str, str],
    ) -> ResolvedIdentity:
        groups_config = self._config.directory.groups
        subject_uid = consumer.uid
        subject_groups = consumer.groups
        if groups_config.asserts_people in consumer.groups:
            person = _header(headers, consumer.consumer_class.headers.person)
            if not person:
                raise AuthorizationError(
                    "la cabecera de persona es obligatoria para esta cuenta"
                )
            entries = self._directory.find(
                "mail",
                person,
                key_attribute=self._config.directory.key_attribute,
            )
            if len(entries) != 1:
                raise AuthorizationError(
                    "la persona afirmada no existe de forma unica"
                )
            selected = entries[0]
            if not selected.uid or groups_config.users not in selected.groups:
                raise AuthorizationError(
                    "la persona afirmada no pertenece al grupo de usuarios"
                )
            subject_uid = selected.uid
            subject_groups = selected.groups
        profile = (
            "adult"
            if groups_config.adult in subject_groups
            and groups_config.child not in subject_groups
            else "child"
        )
        menu = consumer.consumer_class.menu_for(
            profile,
            prototypes=groups_config.prototypes in subject_groups,
        )
        return ResolvedIdentity(
            consumer=consumer.uid,
            consumer_class=consumer.consumer_class,
            user_id=subject_uid,
            service=consumer.consumer_class.name,
            interlocutor_profile=profile,
            menu=menu,
        )


def _bearer_parts(authorization: str | None) -> tuple[str, str]:
    prefix = "Bearer "
    if authorization is None or not authorization.startswith(prefix):
        raise AuthenticationError("falta una clave Bearer valida", "Authorization")
    raw = authorization[len(prefix) :]
    if "." not in raw:
        raise AuthenticationError(
            "la clave Bearer debe tener la forma <uid>.<secreto>", "Authorization"
        )
    uid, secret = raw.split(".", 1)
    if not UID_PATTERN.fullmatch(uid) or not secret:
        raise AuthenticationError(
            "la clave Bearer debe tener la forma <uid>.<secreto>", "Authorization"
        )
    return uid, secret


def _ldap_entry(attributes: dict[str, Any], key_attribute: str) -> DirectoryEntry:
    return DirectoryEntry(
        uid=_single_text(attributes.get("uid")),
        mail=_single_text(attributes.get("mail")),
        groups=frozenset(
            group
            for value in _values(attributes.get("memberOf"))
            if (group := _group_cn(value)) is not None
        ),
        key_sha256=_single_text(attributes.get(key_attribute)),
    )


def _group_cn(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        from ldap3.utils.dn import parse_dn

        for attribute, text, _separator in parse_dn(value):
            if attribute.lower() == "cn":
                return text
    except (ImportError, ValueError, TypeError):
        return None
    return None


def _values(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if value is None:
        return []
    return [value]


def _single_text(value: Any) -> str | None:
    values = _values(value)
    if len(values) != 1 or not isinstance(values[0], str) or not values[0].strip():
        return None
    return values[0].strip()


def _header(headers: Mapping[str, str], name: str | None) -> str | None:
    if name is None:
        return None
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            stripped = value.strip()
            return stripped or None
    return None

"""Punto unico de autenticacion y resolucion de identidades."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Mapping, Protocol

from .config import ConsumerConfig, EdgeConfig, IdentityConfig, MenuEntry
from .errors import AuthenticationError


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    consumer: ConsumerConfig
    user_id: str
    service: str
    interlocutor_profile: str
    menu: tuple[MenuEntry, ...]

    @property
    def default_entry(self) -> MenuEntry:
        return next(item for item in self.menu if item.default)


class IdentityResolver(Protocol):
    """Frontera sustituible de resolucion de identidades."""

    def authenticate(self, authorization: str | None) -> ConsumerConfig: ...

    def resolve(
        self,
        consumer: ConsumerConfig,
        headers: Mapping[str, str],
    ) -> ResolvedIdentity: ...


class FileIdentityResolver:
    """Unica implementacion inicial: identidades declaradas en YAML."""

    def __init__(self, config: EdgeConfig) -> None:
        self._config = config

    def authenticate(self, authorization: str | None) -> ConsumerConfig:
        prefix = "Bearer "
        if authorization is None or not authorization.startswith(prefix):
            raise AuthenticationError(
                "falta una clave Bearer valida", "Authorization"
            )
        key = authorization[len(prefix) :]
        if not key:
            raise AuthenticationError(
                "falta una clave Bearer valida", "Authorization"
            )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        selected = None
        for consumer in self._config.consumers:
            if hmac.compare_digest(digest, consumer.key_sha256):
                selected = consumer
        if selected is None:
            raise AuthenticationError(
                "la clave Bearer no es conocida", "Authorization"
            )
        return selected

    def resolve(
        self,
        consumer: ConsumerConfig,
        headers: Mapping[str, str],
    ) -> ResolvedIdentity:
        identity = consumer.default_identity
        if consumer.can_assert_people:
            person_value = _header(headers, consumer.headers.person)
            identity = consumer.people.get(person_value) if person_value else None
            if identity is None:
                identity = self._config.guest
        return _resolved(consumer, identity)


def _resolved(
    consumer: ConsumerConfig,
    identity: IdentityConfig,
) -> ResolvedIdentity:
    return ResolvedIdentity(
        consumer=consumer,
        user_id=identity.user_id,
        service=consumer.name,
        interlocutor_profile=identity.profile,
        menu=identity.menu,
    )


def _header(headers: Mapping[str, str], name: str | None) -> str | None:
    if name is None:
        return None
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None

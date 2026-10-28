from __future__ import annotations

from dataclasses import replace

import pytest

from ianest_edge.config import EdgeConfig
from ianest_edge.errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DirectoryUnavailableError,
)
from ianest_edge.identity import (
    DirectoryEntry,
    DirectoryIdentityResolver,
    LdapDirectoryClient,
)

from .conftest import BEARER, KEY, KEY_HASH, UID, config_dict


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic x", "Bearer no-point", "Bearer A.bad", "Bearer a."],
)
def test_invalid_bearer_form_never_queries_directory(config, directory, authorization):
    resolver = DirectoryIdentityResolver(config, directory)
    with pytest.raises(AuthenticationError):
        resolver.authenticate(authorization)
    assert directory.calls == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda directory: directory.entries.pop(0),
        lambda directory: directory.entries.__setitem__(
            0,
            DirectoryEntry(UID, "service@test", frozenset(), KEY_HASH),
        ),
        lambda directory: directory.entries.__setitem__(
            0,
            DirectoryEntry(
                UID,
                "service@test",
                frozenset({"ia_nest_services", "edge_class_open_webui"}),
                None,
            ),
        ),
    ],
)
def test_unknown_outside_services_and_missing_key_are_401(
    config, directory, mutation
):
    mutation(directory)
    resolver = DirectoryIdentityResolver(config, directory)
    with pytest.raises(AuthenticationError):
        resolver.authenticate(BEARER)


def test_wrong_secret_is_401(config, directory):
    resolver = DirectoryIdentityResolver(config, directory)
    with pytest.raises(AuthenticationError):
        resolver.authenticate(f"Bearer {UID}.wrong")


@pytest.mark.parametrize(
    ("mail", "profile"),
    [
        ("adult@test", "adult"),
        ("child@test", "child"),
        ("both@test", "child"),
        ("unknown@test", "child"),
    ],
)
def test_person_profile_fails_closed(config, directory, mail, profile):
    resolver = DirectoryIdentityResolver(config, directory)
    account = resolver.authenticate(BEARER)
    identity = resolver.resolve(account, {"X-Person": mail})
    assert identity.interlocutor_profile == profile


@pytest.mark.parametrize("headers", [{}, {"X-Person": "missing@test"}, {"X-Person": "outside@test"}])
def test_asserted_person_must_be_present_unique_and_user(config, directory, headers):
    resolver = DirectoryIdentityResolver(config, directory)
    account = resolver.authenticate(BEARER)
    with pytest.raises(AuthorizationError):
        resolver.resolve(account, headers)


def test_directory_change_applies_on_next_request(config, directory):
    resolver = DirectoryIdentityResolver(config, directory)
    account = resolver.authenticate(BEARER)
    assert resolver.resolve(account, {"X-Person": "adult@test"}).user_id == "adult_user"
    directory.entries = [item for item in directory.entries if item.mail != "adult@test"]
    account = resolver.authenticate(BEARER)
    with pytest.raises(AuthorizationError):
        resolver.resolve(account, {"X-Person": "adult@test"})


@pytest.mark.parametrize(
    "groups",
    [
        {"ia_nest_services"},
        {"ia_nest_services", "edge_class_api", "edge_class_open_webui"},
        {"ia_nest_services", "edge_class_missing"},
    ],
)
def test_account_requires_exactly_one_declared_class(config, directory, groups):
    directory.entries[0] = DirectoryEntry(
        UID, "service@test", frozenset(groups), KEY_HASH
    )
    with pytest.raises(AuthorizationError):
        DirectoryIdentityResolver(config, directory).authenticate(BEARER)


def test_prototype_menu_depends_on_subject_group(config, directory):
    resolver = DirectoryIdentityResolver(config, directory)
    account = resolver.authenticate(BEARER)
    adult = resolver.resolve(account, {"X-Person": "adult@test"})
    child = resolver.resolve(account, {"X-Person": "child@test"})
    assert "iterative" in {item.id for item in adult.menu}
    assert "iterative" not in {item.id for item in child.menu}


def test_account_without_person_assertion_uses_its_own_identity(config, directory):
    resolver = DirectoryIdentityResolver(config, directory)
    identity = resolver.resolve(
        resolver.authenticate(f"Bearer api_service.{KEY}"), {}
    )
    assert identity.user_id == "api_service"
    assert identity.service == "api"
    assert identity.interlocutor_profile == "adult"


def test_directory_unavailable_is_typed_and_recovers(config, directory):
    resolver = DirectoryIdentityResolver(config, directory)
    directory.unavailable = True
    with pytest.raises(DirectoryUnavailableError):
        resolver.authenticate(BEARER)
    directory.unavailable = False
    assert resolver.authenticate(BEARER).uid == UID


@pytest.mark.parametrize("kind", ["refused", "timeout"])
def test_ldap_network_and_timeout_errors_are_directory_unavailable(
    config, monkeypatch, kind
):
    import ldap3
    from ldap3.core.exceptions import (
        LDAPResponseTimeoutError,
        LDAPSocketOpenError,
    )

    captured = {}

    def server(*args, **kwargs):
        captured.update(kwargs)
        return object()

    class FailingConnection:
        def __init__(self, *args, **kwargs):
            pass

        def bind(self):
            if kind == "refused":
                raise LDAPSocketOpenError("refused")
            raise LDAPResponseTimeoutError("timeout")

        def unbind(self):
            return True

    monkeypatch.setattr(ldap3, "Server", server)
    monkeypatch.setattr(ldap3, "Connection", FailingConnection)
    client = LdapDirectoryClient(config.directory)
    with pytest.raises(DirectoryUnavailableError):
        client.find("uid", UID, key_attribute=config.directory.key_attribute)
    assert captured["use_ssl"] is True


@pytest.mark.parametrize(
    ("timeout_seconds", "expected_timeout"), [(3.0, 3), (2.1, 3)]
)
def test_ldap_receive_timeout_is_a_rounded_up_integer(
    config, monkeypatch, timeout_seconds, expected_timeout
):
    import ldap3

    captured = {}

    class Connection:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self.entries = []

        def bind(self):
            return True

        def search(self, *args, **kwargs):
            captured["time_limit"] = kwargs["time_limit"]

        def unbind(self):
            return True

    monkeypatch.setattr(ldap3, "Server", lambda *args, **kwargs: object())
    monkeypatch.setattr(ldap3, "Connection", Connection)
    directory_config = replace(config.directory, timeout_seconds=timeout_seconds)
    client = LdapDirectoryClient(directory_config)

    assert client.find("uid", UID, key_attribute="edge-key-sha256") == []
    assert captured["receive_timeout"] == expected_timeout
    assert isinstance(captured["receive_timeout"], int)
    assert captured["time_limit"] == expected_timeout


def test_ldap_connection_is_reused_and_reopened_after_search_failure(
    config, monkeypatch
):
    import ldap3
    from ldap3.core.exceptions import LDAPSocketOpenError

    class Entry:
        entry_attributes_as_dict = {
            "uid": [UID],
            "mail": ["service@test"],
            "memberOf": [],
            "edge-key-sha256": [KEY_HASH],
        }

    class Connection:
        instances = []
        fail_stale_connection = False

        def __init__(self, *args, **kwargs):
            self.number = len(self.instances)
            self.entries = []
            self.instances.append(self)

        def bind(self):
            return True

        def search(self, *args, **kwargs):
            if self.fail_stale_connection and self.number == 0:
                raise LDAPSocketOpenError("conexion perdida")
            self.entries = [Entry()]

        def unbind(self):
            return True

    monkeypatch.setattr(ldap3, "Server", lambda *args, **kwargs: object())
    monkeypatch.setattr(ldap3, "Connection", Connection)
    client = LdapDirectoryClient(config.directory)

    assert client.find("uid", UID, key_attribute="edge-key-sha256")[0].uid == UID
    assert client.find("uid", UID, key_attribute="edge-key-sha256")[0].uid == UID
    assert len(Connection.instances) == 1
    Connection.fail_stale_connection = True
    assert client.find("uid", UID, key_attribute="edge-key-sha256")[0].uid == UID
    assert client.find("uid", UID, key_attribute="edge-key-sha256")[0].uid == UID
    assert len(Connection.instances) == 2


@pytest.mark.parametrize("legacy", ["consumers", "people", "key_sha256", "guest"])
def test_legacy_identity_keys_are_rejected_anywhere(tmp_path, legacy):
    raw = config_dict(tmp_path)
    raw["classes"]["api"]["nested"] = {legacy: "forbidden"}
    with pytest.raises(ConfigurationError, match="primera entrega"):
        EdgeConfig.from_dict(raw)


def test_directory_requires_ldaps(tmp_path):
    raw = config_dict(tmp_path)
    raw["directory"]["url"] = "ldap://directory.test"
    with pytest.raises(ConfigurationError, match="ldaps"):
        EdgeConfig.from_dict(raw)


def test_menu_without_prototypes_has_one_default(tmp_path):
    raw = config_dict(tmp_path)
    raw["classes"]["api"]["menus"]["adult"][0]["default"] = False
    with pytest.raises(ConfigurationError, match="sin prototipos"):
        EdgeConfig.from_dict(raw)


def test_startup_validates_domains_but_not_directory(service, extended, directory):
    directory.unavailable = True
    service.validate_startup()
    assert extended.calls == [("domain.list", None)]


def test_startup_rejects_unknown_domain(tmp_path, directory, extended):
    raw = config_dict(tmp_path)
    raw["classes"]["api"]["menus"]["adult"][0]["domain"] = "missing"
    config = EdgeConfig.from_dict(raw)
    edge = __import__("ianest_edge").EdgeService(
        config,
        resolver=DirectoryIdentityResolver(config, directory),
        client=extended,
    )
    with pytest.raises(ConfigurationError, match="no existe"):
        edge.validate_startup()

from __future__ import annotations

import hashlib

import pytest

from ianest_edge.config import EdgeConfig
from ianest_edge.errors import AuthenticationError, ConfigurationError
from ianest_edge.identity import FileIdentityResolver

from .conftest import KEY, config_dict


def test_authentication_rejects_before_any_downstream_call(service, extended):
    with pytest.raises(AuthenticationError):
        service.authenticate_and_resolve(None, {})
    with pytest.raises(AuthenticationError):
        service.authenticate_and_resolve("Bearer wrong", {})
    assert extended.calls == []


def test_person_resolution_fails_closed(config):
    resolver = FileIdentityResolver(config)
    consumer = resolver.authenticate(f"Bearer {KEY}")

    declared = resolver.resolve(consumer, {"X-Person": "child"})
    absent = resolver.resolve(consumer, {})
    unknown = resolver.resolve(consumer, {"X-Person": "nobody"})
    bad_profile = resolver.resolve(consumer, {"X-Person": "unknown_profile"})

    assert declared.interlocutor_profile == "child"
    assert absent.user_id == unknown.user_id == "guest"
    assert absent.interlocutor_profile == unknown.interlocutor_profile == "child"
    assert bad_profile.interlocutor_profile == "child"


def test_guest_profile_is_always_child_even_if_config_declares_other(tmp_path):
    raw = config_dict(tmp_path)
    raw["guest"]["profile"] = "adult"

    config = EdgeConfig.from_dict(raw)

    assert config.guest.profile == "child"


def test_person_header_is_ignored_when_consumer_cannot_assert_people(tmp_path):
    raw = config_dict(tmp_path)
    consumer = raw["consumers"]["chat"]
    consumer["can_assert_people"] = False
    config = EdgeConfig.from_dict(raw)
    resolver = FileIdentityResolver(config)
    authenticated = resolver.authenticate(f"Bearer {KEY}")

    resolved = resolver.resolve(authenticated, {"X-Person": "child"})

    assert resolved.user_id == "shared"
    assert resolved.interlocutor_profile == "adult"


def test_key_hash_is_sha256(config):
    assert config.consumers[0].key_sha256 == hashlib.sha256(
        KEY.encode("utf-8")
    ).hexdigest()


def test_write_memory_defaults_to_true(config):
    assert config.consumers[0].write_memory is True


def test_tls_loads_when_certificate_and_key_exist(tmp_path):
    raw = config_dict(tmp_path)
    certfile = tmp_path / "edge-cert.pem"
    keyfile = tmp_path / "edge-key.pem"
    certfile.touch()
    keyfile.touch()
    raw["server"]["tls"] = {
        "certfile": str(certfile),
        "keyfile": str(keyfile),
    }

    config = EdgeConfig.from_dict(raw)

    assert config.tls is not None
    assert config.tls.certfile == certfile
    assert config.tls.keyfile == keyfile


@pytest.mark.parametrize("field", ["certfile", "keyfile"])
def test_tls_rejects_only_one_declared(tmp_path, field):
    raw = config_dict(tmp_path)
    raw["server"]["tls"] = {field: str(tmp_path / f"{field}.pem")}

    with pytest.raises(ConfigurationError, match="certfile y keyfile juntos"):
        EdgeConfig.from_dict(raw)


def test_tls_rejects_missing_file(tmp_path):
    raw = config_dict(tmp_path)
    certfile = tmp_path / "edge-cert.pem"
    certfile.touch()
    missing_keyfile = tmp_path / "missing-key.pem"
    raw["server"]["tls"] = {
        "certfile": str(certfile),
        "keyfile": str(missing_keyfile),
    }

    with pytest.raises(ConfigurationError, match="fichero TLS no existe") as exc_info:
        EdgeConfig.from_dict(raw)

    assert exc_info.value.field == "server.tls.keyfile"


@pytest.mark.parametrize("value", ["false", 0, None])
def test_non_boolean_write_memory_rejects_configuration(tmp_path, value):
    raw = config_dict(tmp_path)
    raw["consumers"]["chat"]["write_memory"] = value

    with pytest.raises(ConfigurationError, match="write_memory debe ser booleano"):
        EdgeConfig.from_dict(raw)


def test_startup_rejects_child_non_direct_mode(tmp_path, extended):
    raw = config_dict(tmp_path)
    raw["guest"]["menu"][0]["mode"] = "razonado"
    config = EdgeConfig.from_dict(raw)
    service = __import__("ianest_edge").EdgeService(
        config, resolver=FileIdentityResolver(config), client=extended
    )

    with pytest.raises(ConfigurationError, match="child"):
        service.validate_startup()


def test_startup_rejects_iterative_fixed_domain(tmp_path, extended):
    raw = config_dict(tmp_path)
    raw["consumers"]["chat"]["people"]["adult"]["menu"][2]["domain"] = "linux"
    config = EdgeConfig.from_dict(raw)
    service = __import__("ianest_edge").EdgeService(
        config, resolver=FileIdentityResolver(config), client=extended
    )

    with pytest.raises(ConfigurationError, match="domain=auto"):
        service.validate_startup()


def test_startup_rejects_unknown_domain(tmp_path, extended):
    raw = config_dict(tmp_path)
    raw["consumers"]["chat"]["people"]["adult"]["menu"][0]["domain"] = "missing"
    config = EdgeConfig.from_dict(raw)
    service = __import__("ianest_edge").EdgeService(
        config, resolver=FileIdentityResolver(config), client=extended
    )

    with pytest.raises(ConfigurationError, match="no existe"):
        service.validate_startup()


def test_startup_accepts_valid_config(service, extended):
    service.validate_startup()
    assert extended.calls == [("domain.list", None)]

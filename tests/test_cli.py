from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from ianest_edge import cli
from ianest_edge import rest
from ianest_edge.config import EdgeConfig

from .conftest import config_dict


@pytest.mark.parametrize("tls_enabled", [False, True])
def test_serve_passes_tls_options_only_when_configured(
    tmp_path, monkeypatch, tls_enabled
):
    raw = config_dict(tmp_path)
    if tls_enabled:
        certfile = tmp_path / "edge-cert.pem"
        keyfile = tmp_path / "edge-key.pem"
        certfile.touch()
        keyfile.touch()
        raw["server"]["tls"] = {
            "certfile": str(certfile),
            "keyfile": str(keyfile),
        }
    config = EdgeConfig.from_dict(raw)
    captured = {}

    def run(app, **options):
        captured["app"] = app
        captured["options"] = options

    monkeypatch.setattr(cli.EdgeConfig, "from_env", classmethod(lambda cls: config))
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=run))
    monkeypatch.setattr(rest, "create_app", lambda **kwargs: object())
    monkeypatch.setattr(sys, "argv", ["ianest-edge", "serve"])

    cli.main()

    assert captured["options"]["host"] == config.host
    assert captured["options"]["port"] == config.port
    if tls_enabled:
        assert captured["options"]["ssl_certfile"] == str(certfile)
        assert captured["options"]["ssl_keyfile"] == str(keyfile)
    else:
        assert "ssl_certfile" not in captured["options"]
        assert "ssl_keyfile" not in captured["options"]

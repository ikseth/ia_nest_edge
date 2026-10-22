"""Entrada de consola del servicio y generador de claves."""

from __future__ import annotations

import argparse
import hashlib
import secrets

from .config import EdgeConfig
from .identity import FileIdentityResolver
from .service import EdgeService


def generate_key() -> tuple[str, str]:
    key = secrets.token_urlsafe(32)
    return key, hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_main() -> None:
    key, digest = generate_key()
    print(f"key: {key}")
    print(f"sha256: {digest}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ianest-edge")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="arranca el servicio HTTP")
    subparsers.add_parser("key", help="genera una clave y su hash SHA-256")
    args = parser.parse_args()
    if args.command == "key":
        key_main()
        return
    if args.command not in {None, "serve"}:
        parser.error("subcomando desconocido")
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depende de la instalacion
        raise RuntimeError("uvicorn no esta instalado") from exc
    from .rest import create_app

    config = EdgeConfig.from_env()
    service = EdgeService(config, resolver=FileIdentityResolver(config))
    run_options = {
        "host": config.host,
        "port": config.port,
    }
    if config.tls is not None:
        run_options["ssl_certfile"] = str(config.tls.certfile)
        run_options["ssl_keyfile"] = str(config.tls.keyfile)
    uvicorn.run(create_app(config=config, service=service), **run_options)

"""Entrada de consola del servicio y generador de claves."""

from __future__ import annotations

import argparse
import hashlib
import secrets

from .config import EdgeConfig
from .identity import DirectoryIdentityResolver
from .service import EdgeService


def generate_key() -> tuple[str, str]:
    key = secrets.token_urlsafe(32)
    return key, hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ianest-edge-key",
        description=_key_help(),
    )
    parser.parse_args(argv)
    key, digest = generate_key()
    print(f"key: {key}")
    print(f"sha256: {digest}")


def _key_help() -> str:
    return (
        "genera el secreto para Bearer <uid>.<secreto> y el hash SHA-256 "
        "que se guarda en el atributo de la cuenta"
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="ianest-edge")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="arranca el servicio HTTP")
    subparsers.add_parser("key", help=_key_help())
    args = parser.parse_args()
    if args.command == "key":
        key_main([])
        return
    if args.command not in {None, "serve"}:
        parser.error("subcomando desconocido")
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depende de la instalacion
        raise RuntimeError("uvicorn no esta instalado") from exc
    from .rest import create_app

    config = EdgeConfig.from_env()
    service = EdgeService(config, resolver=DirectoryIdentityResolver(config))
    run_options = {
        "host": config.host,
        "port": config.port,
    }
    if config.tls is not None:
        run_options["ssl_certfile"] = str(config.tls.certfile)
        run_options["ssl_keyfile"] = str(config.tls.keyfile)
    uvicorn.run(create_app(config=config, service=service), **run_options)

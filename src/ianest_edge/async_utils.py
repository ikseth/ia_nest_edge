"""Puente minimo para ejecutar adaptadores bloqueantes desde ASGI."""

from __future__ import annotations

import asyncio
import contextvars
import threading
from collections.abc import Callable
from typing import Any


async def run_sync(function: Callable[..., Any], *args: Any) -> Any:
    """Ejecuta una llamada bloqueante sin bloquear el bucle ASGI."""
    context = contextvars.copy_context()
    completed = threading.Event()
    outcome: list[Any] = []

    def invoke() -> None:
        try:
            outcome.append((True, context.run(function, *args)))
        except BaseException as exc:
            outcome.append((False, exc))
        finally:
            completed.set()

    threading.Thread(target=invoke, daemon=True).start()
    while not completed.is_set():
        await asyncio.sleep(0.001)
    succeeded, value = outcome[0]
    if succeeded:
        return value
    raise value

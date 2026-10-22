"""Errores propios y reenviados por el borde."""

from __future__ import annotations

from typing import Any

EDGE_ORIGIN = "ia_nest_edge"


class EdgeError(Exception):
    """Error propio con la forma comun del ente."""

    status_code = 400

    def __init__(
        self,
        message: str,
        field: str | None = None,
        *,
        error_type: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.type = error_type or type(self).__name__
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "field": self.field,
            "origin": EDGE_ORIGIN,
        }


class AuthenticationError(EdgeError):
    status_code = 401


class RequestValidationError(EdgeError):
    pass


class ConfigurationError(EdgeError):
    status_code = 500


class ExtendedConnectionError(EdgeError):
    status_code = 503


class ExtendedResponseError(EdgeError):
    status_code = 502


class DownstreamError(Exception):
    """Error de extended o core conservado sin re-tipar."""

    def __init__(self, error: dict[str, Any], status_code: int) -> None:
        super().__init__(str(error.get("message", "downstream error")))
        self.error = dict(error)
        self.status_code = status_code

"""Borde autenticador REST, MCP y OpenAI de IA_NEST."""

from .audit import AuditRecord, AuditWriter
from .client import ExtendedClient, ExtendedHttpClient, SseEvent
from .config import EdgeConfig
from .identity import DirectoryIdentityResolver, IdentityResolver, ResolvedIdentity
from .service import EdgeService

__all__ = [
    "AuditRecord",
    "AuditWriter",
    "EdgeConfig",
    "EdgeService",
    "ExtendedClient",
    "ExtendedHttpClient",
    "DirectoryIdentityResolver",
    "IdentityResolver",
    "ResolvedIdentity",
    "SseEvent",
]

__version__ = "0.2.0"

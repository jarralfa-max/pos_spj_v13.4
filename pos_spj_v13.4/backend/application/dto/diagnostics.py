"""Explicit result DTO for external-integration diagnostics (FASE 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DiagnosticResult:
    """Outcome of an external integration probe. Errors are explicit, never silent."""

    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, message: str, **data: Any) -> "DiagnosticResult":
        return cls(ok=True, message=message, data=dict(data))

    @classmethod
    def failure(cls, message: str, **data: Any) -> "DiagnosticResult":
        return cls(ok=False, message=message, data=dict(data))

"""Structured result returned by HR use cases.

Use cases never raise for known domain errors to the UI; they translate them
into a structured result the presenter maps to a friendly message. Unexpected
errors propagate (logged with context, shown generically) — never swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class HRResult:
    success: bool
    message: str = ""
    operation_id: str | None = None
    entity_id: str | None = None
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", *, entity_id: str | None = None,
           operation_id: str | None = None, **data) -> "HRResult":
        return cls(True, message, operation_id, entity_id, None, dict(data))

    @classmethod
    def fail(cls, message: str, error_code: str, *, operation_id: str | None = None) -> "HRResult":
        return cls(False, message, operation_id, None, error_code, {})

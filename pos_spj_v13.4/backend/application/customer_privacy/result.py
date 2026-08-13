"""Structured result returned by Customer Privacy use cases. Mirrors
backend/application/customer_credit/result.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CustomerPrivacyResult:
    success: bool
    message: str = ""
    operation_id: str | None = None
    entity_id: str | None = None
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", *, entity_id: str | None = None,
           operation_id: str | None = None, **data) -> "CustomerPrivacyResult":
        return cls(True, message, operation_id, entity_id, None, dict(data))

    @classmethod
    def fail(cls, message: str, error_code: str, *,
             operation_id: str | None = None, **data) -> "CustomerPrivacyResult":
        return cls(False, message, operation_id, None, error_code, dict(data))

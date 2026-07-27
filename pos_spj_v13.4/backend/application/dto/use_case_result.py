"""DTOs returned by application use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.shared.events import DomainEvent


@dataclass(frozen=True)
class UseCaseResult:
    success: bool
    operation_id: str
    entity_id: str | None = None
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    events: tuple[DomainEvent, ...] = ()

    @classmethod
    def not_implemented(cls, operation_id: str, *, use_case_name: str) -> "UseCaseResult":
        return cls(
            success=False,
            operation_id=operation_id,
            message=f"{use_case_name} is not wired yet.",
        )

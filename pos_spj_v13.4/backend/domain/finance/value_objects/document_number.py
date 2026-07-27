"""DocumentNumber value object — human-visible folio; never a primary key."""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.finance.exceptions import FinanceDomainError


@dataclass(frozen=True, slots=True)
class DocumentNumber:
    """Commercial reference (folio). Identity is always the UUIDv7 ``id``."""

    value: str

    def __post_init__(self) -> None:
        cleaned = (self.value or "").strip()
        if not cleaned or len(cleaned) > 40:
            raise FinanceDomainError(f"Invalid document number: {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value

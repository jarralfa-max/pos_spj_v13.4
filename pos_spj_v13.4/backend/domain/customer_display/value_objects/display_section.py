"""DisplaySection — SET-17 "Layouts": one named, ordered, toggleable
block of a `DisplayLayout`. Mirrors
`backend.domain.document_output.value_objects.document_section.DocumentSection`'s
shape (independently defined, not imported — bounded-context
independence).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.customer_display.enums import CustomerDisplaySectionCode
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError


@dataclass(frozen=True, slots=True)
class DisplaySection:
    code: CustomerDisplaySectionCode
    order: int
    enabled: bool = True

    @classmethod
    def create(
        cls, *, code: CustomerDisplaySectionCode, order: int, enabled: bool = True,
    ) -> "DisplaySection":
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise CustomerDisplayInvalidValueError(f"order debe ser un entero >= 0, recibido {order!r}")
        return cls(code=code, order=order, enabled=bool(enabled))

"""CustomerCode — the human-facing folio, distinct from the UUIDv7 `id` (§11,
"Los folios comerciales deben ser campos separados"). Mirrors
backend/domain/suppliers/value_objects.py::SupplierCode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.customers.exceptions import InvalidCustomerCodeError

_CODE_RE = re.compile(r"^CLI-\d{6,}$")


@dataclass(frozen=True, slots=True)
class CustomerCode:
    value: str

    def __post_init__(self) -> None:
        if not _CODE_RE.match(self.value or ""):
            raise InvalidCustomerCodeError(
                f"customer_number inválido: {self.value!r} (usa CLI-NNNNNN)")

    @classmethod
    def from_sequence(cls, sequence: int) -> "CustomerCode":
        return cls(f"CLI-{int(sequence):06d}")

    def __str__(self) -> str:
        return self.value

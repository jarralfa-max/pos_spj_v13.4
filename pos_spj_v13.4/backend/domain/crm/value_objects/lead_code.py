"""LeadCode — the human-facing folio, distinct from the UUIDv7 `id` (§11,
"Los folios comerciales deben ser campos separados"). Mirrors
backend/domain/customers/value_objects/customer_code.py::CustomerCode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.crm.exceptions import InvalidLeadCodeError

_CODE_RE = re.compile(r"^LEAD-\d{6,}$")


@dataclass(frozen=True, slots=True)
class LeadCode:
    value: str

    def __post_init__(self) -> None:
        if not _CODE_RE.match(self.value or ""):
            raise InvalidLeadCodeError(
                f"lead_number inválido: {self.value!r} (usa LEAD-NNNNNN)")

    @classmethod
    def from_sequence(cls, sequence: int) -> "LeadCode":
        return cls(f"LEAD-{int(sequence):06d}")

    def __str__(self) -> str:
        return self.value

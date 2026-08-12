"""OpportunityCode — the human-facing folio, distinct from the UUIDv7 `id`
(§11, "Los folios comerciales deben ser campos separados"). Mirrors
backend/domain/crm/value_objects/lead_code.py::LeadCode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.crm.exceptions import InvalidOpportunityCodeError

_CODE_RE = re.compile(r"^OPP-\d{6,}$")


@dataclass(frozen=True, slots=True)
class OpportunityCode:
    value: str

    def __post_init__(self) -> None:
        if not _CODE_RE.match(self.value or ""):
            raise InvalidOpportunityCodeError(
                f"opportunity_number inválido: {self.value!r} (usa OPP-NNNNNN)")

    @classmethod
    def from_sequence(cls, sequence: int) -> "OpportunityCode":
        return cls(f"OPP-{int(sequence):06d}")

    def __str__(self) -> str:
        return self.value

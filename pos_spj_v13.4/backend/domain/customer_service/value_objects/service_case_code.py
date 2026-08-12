"""ServiceCaseCode — the human-facing folio, distinct from the UUIDv7 `id`
(§11). Mirrors backend/domain/crm/value_objects/opportunity_code.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.customer_service.exceptions import InvalidServiceCaseCodeError

_CODE_RE = re.compile(r"^CASE-\d{6,}$")


@dataclass(frozen=True, slots=True)
class ServiceCaseCode:
    value: str

    def __post_init__(self) -> None:
        if not _CODE_RE.match(self.value or ""):
            raise InvalidServiceCaseCodeError(
                f"case_number inválido: {self.value!r} (usa CASE-NNNNNN)")

    @classmethod
    def from_sequence(cls, sequence: int) -> "ServiceCaseCode":
        return cls(f"CASE-{int(sequence):06d}")

    def __str__(self) -> str:
        return self.value

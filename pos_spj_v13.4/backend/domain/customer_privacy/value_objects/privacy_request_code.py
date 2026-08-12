"""PrivacyRequestCode — the human-facing folio, distinct from the UUIDv7
`id` (§11). Mirrors
backend/domain/customer_service/value_objects/service_case_code.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.customer_privacy.exceptions import InvalidPrivacyRequestCodeError

_CODE_RE = re.compile(r"^PRIV-\d{6,}$")


@dataclass(frozen=True, slots=True)
class PrivacyRequestCode:
    value: str

    def __post_init__(self) -> None:
        if not _CODE_RE.match(self.value or ""):
            raise InvalidPrivacyRequestCodeError(
                f"request_number inválido: {self.value!r} (usa PRIV-NNNNNN)")

    @classmethod
    def from_sequence(cls, sequence: int) -> "PrivacyRequestCode":
        return cls(f"PRIV-{int(sequence):06d}")

    def __str__(self) -> str:
        return self.value

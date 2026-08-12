"""PhoneNumber — strict E.164 value object (§14, §19 "todo teléfono debe usar
estándar WhatsApp/E.164"). Mirrors backend/domain/hr/value_objects.py::PhoneE164.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.customers.exceptions import InvalidPhoneNumberError

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    value: str
    allows_whatsapp: bool = False

    def __post_init__(self) -> None:
        cleaned = (self.value or "").strip().replace(" ", "")
        if not _E164.match(cleaned):
            raise InvalidPhoneNumberError(
                f"Teléfono no está en formato E.164: {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value

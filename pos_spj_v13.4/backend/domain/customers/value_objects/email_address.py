"""EmailAddress — validated, normalized value object (§14). Mirrors
backend/domain/hr/value_objects.py::Email.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.customers.exceptions import InvalidEmailAddressError

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str
    is_marketing_channel: bool = False

    def __post_init__(self) -> None:
        cleaned = (self.value or "").strip().lower()
        if not _EMAIL.match(cleaned):
            raise InvalidEmailAddressError(f"Correo inválido: {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value

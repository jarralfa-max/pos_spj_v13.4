"""AccountCode value object — hierarchical chart-of-accounts code."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.finance.exceptions import FinanceDomainError

_CODE_PATTERN = re.compile(r"^\d{3,4}(\.\d{1,4})*$")


@dataclass(frozen=True, slots=True)
class AccountCode:
    """Numeric dotted code, e.g. ``1105`` or ``1105.01``. Never an identity."""

    value: str

    def __post_init__(self) -> None:
        if not _CODE_PATTERN.match(self.value or ""):
            raise FinanceDomainError(f"Invalid account code: {self.value!r}")

    def is_child_of(self, parent: "AccountCode") -> bool:
        return self.value.startswith(parent.value + ".")

    def __str__(self) -> str:
        return self.value

"""AccountCode value object — hierarchical chart-of-accounts code."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.finance.exceptions import FinanceDomainError

_CODE_PATTERN = re.compile(r"^\d{3,4}(\.\d{1,4})*$")


@dataclass(frozen=True, slots=True)
class AccountCode:
    """Numeric dotted code, e.g. ``1105`` or ``1105.01``. Never an identity.

    Jerarquía: ``1105.01`` desciende de ``1105``; en códigos de cuatro dígitos
    los ceros finales del padre marcan el nivel (``1100`` agrupa ``11xx`` y
    ``1000`` agrupa ``1xxx``).
    """

    value: str

    def __post_init__(self) -> None:
        if not _CODE_PATTERN.match(self.value or ""):
            raise FinanceDomainError(f"Código de cuenta inválido: {self.value!r}")

    def is_child_of(self, parent: "AccountCode") -> bool:
        return self.value.startswith(parent.value + ".")

    def is_descendant_of(self, parent: "AccountCode") -> bool:
        if self.value == parent.value:
            return False
        if self.is_child_of(parent):
            return True
        if "." in parent.value:
            return False
        prefix = parent.value.rstrip("0")
        if not prefix:
            return False
        return self.value.split(".")[0].startswith(prefix) and \
            len(self.value.split(".")[0]) == len(parent.value)

    def __str__(self) -> str:
        return self.value

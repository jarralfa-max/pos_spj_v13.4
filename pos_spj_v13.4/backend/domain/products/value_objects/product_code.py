"""ProductCode — the human-facing internal SKU (§17).

Not the identity (that is always a UUIDv7). The code is a normalized, unique
business key used on labels, search and supplier mapping. It never substitutes
the UUID (§38 legacy rule) and never carries spaces or lowercase drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.domain.products.exceptions import ProductsDomainError

_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._\-/]{1,63}$")


@dataclass(frozen=True)
class ProductCode:
    value: str

    def __post_init__(self) -> None:
        raw = (self.value or "").strip().upper()
        if not raw:
            raise ProductsDomainError("El código de producto no puede estar vacío")
        if not _CODE_RE.match(raw):
            raise ProductsDomainError(
                f"Código de producto inválido: {self.value!r} "
                "(use A-Z, 0-9, . _ - / ; 2-64 caracteres)")
        object.__setattr__(self, "value", raw)

    def __str__(self) -> str:
        return self.value

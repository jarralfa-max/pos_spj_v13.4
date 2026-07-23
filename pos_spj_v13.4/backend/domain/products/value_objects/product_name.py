"""ProductName — display name plus its search-normalized form (§20 regla 20).

The commercial name is shown to the user (es-MX); ``normalized`` is the
accent/case-folded form used for search and duplicate detection. Both live in the
value object so the rest of the domain never re-derives normalization ad hoc.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from backend.domain.products.exceptions import ProductsDomainError

_MAX = 160


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.split())


@dataclass(frozen=True)
class ProductName:
    value: str
    normalized: str = ""

    def __post_init__(self) -> None:
        raw = " ".join((self.value or "").split())
        if len(raw) < 2:
            raise ProductsDomainError("El nombre de producto es demasiado corto")
        if len(raw) > _MAX:
            raise ProductsDomainError(
                f"El nombre de producto excede {_MAX} caracteres")
        object.__setattr__(self, "value", raw)
        object.__setattr__(self, "normalized", normalize_name(raw))

    def __str__(self) -> str:
        return self.value

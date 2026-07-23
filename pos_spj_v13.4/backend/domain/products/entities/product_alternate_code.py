"""ProductAlternateCode — a non-barcode alternate identifier (§17).

Supplier catalog codes, customer part numbers, legacy codes: a product may be
found by several external codes without any of them being the identity (UUID) or a
scannable barcode. An alternate code may be scoped to a supplier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import ProductsDomainError
from backend.shared.ids import new_uuid


@dataclass
class ProductAlternateCode:
    product_id: str
    code: str
    code_type: str = "SUPPLIER_CODE"
    id: str = field(default_factory=new_uuid)
    supplier_id: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        if not self.product_id:
            raise ProductsDomainError("El código alterno requiere producto")
        code = (self.code or "").strip()
        if not code:
            raise ProductsDomainError("El código alterno no puede estar vacío")
        object.__setattr__(self, "code", code)

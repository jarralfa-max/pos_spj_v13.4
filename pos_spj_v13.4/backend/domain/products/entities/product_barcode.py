"""ProductBarcode — a barcode assigned to a product (or variant) (§17).

Binds a validated ``Barcode`` value to a product. One product may carry many
barcodes (retail EAN, scale barcode, supplier-printed), but an *active* barcode
value must be unique across products (enforced by the uniqueness policy + a DB
UNIQUE index on active rows). One may be flagged primary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidBarcodeError
from backend.domain.products.value_objects.barcode import Barcode
from backend.shared.ids import new_uuid


@dataclass
class ProductBarcode:
    product_id: str
    barcode: Barcode
    id: str = field(default_factory=new_uuid)
    variant_id: str | None = None
    is_primary: bool = False
    active: bool = True

    def __post_init__(self) -> None:
        if not self.product_id:
            raise InvalidBarcodeError("El código de barras requiere producto")
        if not isinstance(self.barcode, Barcode):
            raise InvalidBarcodeError("barcode debe ser un value object Barcode")

    @property
    def value(self) -> str:
        return self.barcode.value

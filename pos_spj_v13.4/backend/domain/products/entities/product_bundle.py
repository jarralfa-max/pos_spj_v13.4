"""ProductBundle — the master record of a combo / kit / package (§28).

Bound to the bundle's own product SKU and its type (virtual vs stocked, meat box,
gift set…). A virtual bundle is exploded at sale; a stocked kit carries its own
stock. The concrete composition lives in its versions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.bundle_enums import STOCKED_TYPES, BundleType
from backend.domain.products.exceptions import InvalidBundleError
from backend.shared.ids import new_uuid


@dataclass
class ProductBundle:
    product_id: str
    bundle_type: BundleType
    name: str
    id: str = field(default_factory=new_uuid)
    active: bool = True

    def __post_init__(self) -> None:
        if not self.product_id:
            raise InvalidBundleError("El combo requiere producto")
        if not (self.name or "").strip():
            raise InvalidBundleError("El combo requiere un nombre")
        if not isinstance(self.bundle_type, BundleType):
            try:
                self.bundle_type = BundleType(str(self.bundle_type))
            except ValueError as exc:
                raise InvalidBundleError(
                    f"Tipo de combo inválido: {self.bundle_type!r}") from exc

    @property
    def is_stocked(self) -> bool:
        """Un kit stocked se arma previamente y mantiene stock propio (§28)."""
        return self.bundle_type in STOCKED_TYPES

    @property
    def is_virtual(self) -> bool:
        """Un combo virtual se descompone al vender (sin stock propio) (§28)."""
        return not self.is_stocked

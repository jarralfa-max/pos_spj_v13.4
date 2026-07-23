"""ProductLogisticsProfile — weights, dimensions and cold-chain flags (§18).

Weights are Decimal; storage/transport temperature bands are TemperatureRange
value objects. If the product is frozen/chilled it requires a cold chain, which
Inventory (INV-9) enforces at capture time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.value_objects.temperature_range import TemperatureRange
from backend.shared.ids import new_uuid


def _dec(value, label: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise ProductsDomainError(f"{label} no puede ser float")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProductsDomainError(f"{label} inválido") from exc
    if d < 0:
        raise ProductsDomainError(f"{label} no puede ser negativo")
    return d


@dataclass
class ProductLogisticsProfile:
    product_id: str
    id: str = field(default_factory=new_uuid)
    gross_weight: Decimal | None = None
    net_weight: Decimal | None = None
    weight_unit: str = "KG"
    dimensions: str | None = None            # "LxWxH" libre
    storage_temperature: TemperatureRange | None = None
    transport_temperature: TemperatureRange | None = None
    fragile: bool = False
    perishable: bool = False
    frozen: bool = False
    chilled: bool = False
    stackable: bool = True
    shelf_life_days: int = 0
    open_package_shelf_life_days: int = 0
    requires_cold_chain: bool = False

    def __post_init__(self) -> None:
        if not self.product_id:
            raise ProductsDomainError("El perfil logístico requiere producto")
        self.gross_weight = _dec(self.gross_weight, "gross_weight")
        self.net_weight = _dec(self.net_weight, "net_weight")
        if (self.gross_weight is not None and self.net_weight is not None
                and self.net_weight > self.gross_weight):
            raise ProductsDomainError("El peso neto no puede exceder el bruto")
        # frozen/chilled ⇒ cadena de frío (§18)
        if self.frozen or self.chilled:
            self.requires_cold_chain = True

"""Canonical product-master commands (PROD-19 paso 7b — alta/edición born-clean).

Master data ONLY: identidad, clasificación, unidad base y flags de capacidad. El
precio vive en Pricing (`product_price`) y la existencia en Inventory
(`inventory_balances`) — nunca en el maestro (guardrail
`test_product_master_does_not_own_pricing`). UUIDv7 como única identidad.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreateProductMasterCommand:
    operation_id: str
    code: str
    name: str
    product_type: str
    base_unit_id: str
    user_id: str | None = None
    short_name: str | None = None
    description: str | None = None
    category_id: str | None = None
    species_id: str | None = None
    lifecycle_status: str = "DRAFT"
    sellable: bool = True
    purchasable: bool = True
    inventory_managed: bool = True
    producible: bool = False
    internal_only: bool = False
    recipe_allowed: bool = False
    bundle_allowed: bool = False
    lot_controlled: bool = False
    expiration_controlled: bool = False
    catch_weight_enabled: bool = False
    quality_controlled: bool = False
    traceability_required: bool = False

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "code", "name", "product_type",
                               "base_unit_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class UpdateProductMasterCommand(CreateProductMasterCommand):
    product_id: str = ""

    def validate(self) -> None:
        super().validate()
        if not self.product_id:
            raise ValueError("Falta product_id para actualizar")

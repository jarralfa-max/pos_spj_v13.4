"""SellableAvailabilityQueryService — direct + reconstructible availability
(ERP integration master prompt §15-19, Fase 7).

ATP = direct stock + stock reconstructible from the parts of the product's
reversible CUTTING SCHEME (§17; la fuente es el esquema de corte desde el
2026-09-19, decisión del usuario). Composes two already-canonical reads —
`InventoryAvailabilityQueryService` (direct, per product) and
`CuttingSchemeRepository.reversible_active_version_for_input` (is this product's
despiece eligible, and what does it need) — plus the pure
`ReverseRecipeExplosionService` bottleneck calculation. Never writes
anything; the actual reconstruction (reserving parts, consuming them,
producing the base product) is `ReconstructBaseProductUseCase`'s job.

Conservative by design, same discipline as every other cross-context
resolution built this session: any ambiguity (no eligible despiece, more
than one, `reverse_reconstruction_allowed=False`)
resolves to `reconstructible = 0`, never a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from backend.application.inventory.queries.availability_query_service import (
    InventoryAvailabilityQueryService,
)
from backend.domain.products.exceptions import InvalidRecipeError
from backend.domain.products.services.reverse_recipe_explosion_service import (
    ReverseRecipeExplosionService,
)
from backend.infrastructure.db.repositories.products.cutting_scheme_repository import (
    CuttingSchemeRepository,
)

_Z = Decimal("0")


@dataclass(frozen=True, slots=True)
class SellableAvailability:
    product_id: str
    branch_id: str
    direct: Decimal = _Z
    reconstructible: Decimal = _Z
    reserved: Decimal = _Z
    available_to_promise: Decimal = _Z
    #: the reversible cutting-scheme version that made reconstruction possible, or
    #: None when reconstructible == 0 (nothing eligible, or genuinely 0
    #: reconstructible units from what's on hand).
    cutting_scheme_version_id: str | None = None
    #: Un COMPUESTO (receta de venta o combo de Productos) no se almacena: lo
    #: que se puede vender es lo que alcanza su componente más escaso.
    composite_buildable: Decimal = _Z


class SellableAvailabilityQueryService:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._inventory = InventoryAvailabilityQueryService(connection)
        self._cutting = CuttingSchemeRepository(connection)
        self._explosion = ReverseRecipeExplosionService()

    def _composite_buildable(self, product_id, branch_id, warehouse_id) -> Decimal:
        from backend.application.products.queries.sales_fulfillment_query_service import (
            CompositeDefinitionError,
            SalesFulfillmentQueryService,
        )
        try:
            partes = SalesFulfillmentQueryService(self._connection).explode(
                product_id, Decimal("1"))
        except CompositeDefinitionError:
            return _Z                      # composición inválida: no se promete nada
        if set(partes) == {product_id}:
            return _Z
        alcanza = None
        for componente, por_unidad in partes.items():
            if por_unidad <= 0:
                continue
            disponible = self._inventory.get_availability(
                product_id=componente, branch_id=branch_id,
                warehouse_id=warehouse_id).available
            unidades = (Decimal(str(disponible)) / por_unidad).quantize(
                Decimal("0.001"), rounding=ROUND_DOWN)
            alcanza = unidades if alcanza is None else min(alcanza, unidades)
        return max(alcanza or _Z, _Z)

    def get_sellable_availability(
        self, *, product_id: str, branch_id: str, warehouse_id: str | None = None,
    ) -> SellableAvailability:
        direct_dto = self._inventory.get_availability(
            product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id)

        reconstructible = _Z
        cutting_scheme_version_id = None
        version = self._cutting.reversible_active_version_for_input(product_id)
        if version is not None:
            available_by_part = {
                output.product_id: self._inventory.get_availability(
                    product_id=output.product_id, branch_id=branch_id,
                    warehouse_id=warehouse_id).available
                for output in version.outputs
            }
            try:
                reconstructible = self._explosion.max_reconstructible_units(
                    version, available_by_part)
            except InvalidRecipeError:
                reconstructible = _Z
            if reconstructible > 0:
                cutting_scheme_version_id = version.id

        armable = self._composite_buildable(product_id, branch_id, warehouse_id)
        available_to_promise = direct_dto.available + reconstructible + armable
        return SellableAvailability(
            composite_buildable=armable,
            product_id=product_id, branch_id=branch_id,
            direct=direct_dto.available, reconstructible=reconstructible,
            reserved=direct_dto.reserved, available_to_promise=available_to_promise,
            cutting_scheme_version_id=cutting_scheme_version_id)

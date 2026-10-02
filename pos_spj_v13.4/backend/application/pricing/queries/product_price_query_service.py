"""ProductPriceQueryService / ProductCostQueryService (PRC-4).

The canonical read side POS/Ventas/BI consume instead of reading `productos.precio`
or `precios_lista`. ``get_sale_price`` fetches the BASE / CHANNEL / CUSTOMER prices
+ volume tiers for a product/branch/customer/quantity and delegates to
``PricingResolutionService``. ``get_average_cost`` returns the canonical cost.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.services.pricing_resolution_service import (
    PriceResolution,
    PricingResolutionService,
)
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)


class ProductPriceQueryService:
    def __init__(self, connection) -> None:
        self._repo = PricingRepository(connection)
        self._resolver = PricingResolutionService()

    def get_sale_price(
        self,
        product_id: str,
        *,
        branch_id: str | None = None,
        customer_id: str | None = None,
        channel: str | None = None,
        quantity: Decimal | int | str = Decimal("1"),
        on_date: str | None = None,
    ) -> PriceResolution:
        qty = Decimal(str(quantity))
        # Fecha para la vigencia de cada precio (hoy si no se indica).
        from datetime import date as _date
        dia = (on_date or _date.today().isoformat())[:10]

        def _vigente(lista_id: str):
            return self._repo.effective_price(price_list_id=lista_id, product_id=product_id,
                                              branch_id=branch_id, on_date=dia)

        base_list = self._repo.active_list_of_kind(PriceListKind.BASE)
        base_pp = _vigente(base_list.id) if base_list else None
        base_price = base_pp.sale_price if base_pp else None
        min_price = base_pp.min_price if base_pp else None

        # lista de canal (opcional) sustituye la lista si existe precio
        list_price = None
        discount_pct = base_list.discount_pct if base_list else Decimal("0")
        # Sólo la lista del canal PEDIDO (antes: cualquier lista de canal, en
        # todos los canales).
        channel_list = self._repo.active_channel_list(channel)
        ch_pp = None
        if channel_list is not None:
            ch_pp = _vigente(channel_list.id)
            if ch_pp is not None:
                list_price = ch_pp.sale_price
                discount_pct = channel_list.discount_pct

        # lista de cliente
        customer_price = None
        customer_pp = None
        if customer_id:
            cl_id = self._repo.customer_list_id(customer_id)
            if cl_id:
                customer_pp = _vigente(cl_id)
                if customer_pp is not None:
                    customer_price = customer_pp.sale_price
                    cl = self._repo.get_list(cl_id)
                    if cl is not None:
                        discount_pct = cl.discount_pct

        # tiers por volumen sobre el precio aplicable (cliente > canal > base)
        volume_price = None
        applicable_pp = customer_pp or (ch_pp if channel_list and ch_pp else None) or base_pp
        if applicable_pp is not None:
            best: Money | None = None
            for tier in self._repo.volume_tiers(applicable_pp.id):
                if tier.applies_to(qty):
                    if best is None or tier.price < best:
                        best = tier.price
            volume_price = best

        return self._resolver.resolve(
            base_price=base_price, list_price=list_price, customer_price=customer_price,
            volume_price=volume_price, discount_pct=discount_pct, min_price=min_price)


class ProductCostQueryService:
    """Costo que RIGE según la política (§32). Con GLOBAL se ignora la sucursal
    aunque exista su fila (la proyección las mantiene siempre); con PER_BRANCH se
    usa la de la sucursal y, si aún no tiene historia, la de empresa."""

    def __init__(self, connection) -> None:
        from backend.application.pricing.cost_policy import CostPolicySettings
        self._repo = PricingRepository(connection)
        self._policy = CostPolicySettings(connection)

    def _cost(self, product_id: str, branch_id: str | None):
        from backend.application.pricing.cost_policy import CostPolicy
        if self._policy.current() is CostPolicy.PER_BRANCH:
            return self._repo.get_cost(product_id, branch_id)   # sucursal → empresa
        # GLOBAL: el de empresa; sólo si no existe, el de la sucursal (datos que
        # únicamente se costearon por sucursal no deben quedar "sin costo").
        return self._repo.get_cost(product_id, None) or (
            self._repo.get_cost(product_id, branch_id) if branch_id else None)

    def get_average_cost(self, product_id: str, branch_id: str | None = None) -> Money | None:
        cost = self._cost(product_id, branch_id)
        return cost.average_cost if cost else None

    def get_effective_cost(self, product_id: str, branch_id: str | None = None) -> Money | None:
        cost = self._cost(product_id, branch_id)
        return cost.effective_cost() if cost else None

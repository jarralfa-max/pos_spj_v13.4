"""Cuánto beneficio admite una venta sin comerse el margen (auditoría
Fidelidad 968e0bc FID-03). Ventas aporta líneas y costo (`sale_unit_costs`, la
misma regla del cobro); Fidelidad, el margen mínimo por categoría/producto."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.loyalty.policies.benefit_budget_policy import (
    BenefitBudget,
    BenefitBudgetPolicy,
    BudgetLine,
)

MIN_MARGIN_KEY = "loyalty.benefit_min_margin_percent"


class SaleBenefitBudgetQuery:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _default_margin(self) -> Decimal:
        try:
            from backend.application.settings.configuration_reader import ConfigurationReader
            return Decimal(str(ConfigurationReader(self._conn).get(MIN_MARGIN_KEY))) / 100
        except Exception:  # noqa: BLE001 - sin gobierno de ajustes rige el de catálogo
            return Decimal("0.10")

    def margins(self, product_ids) -> dict[str, Decimal]:
        """Margen mínimo (fracción) por producto: excepción del producto, si no
        la categoría más cercana con margen, si no el general."""
        from backend.infrastructure.db.repositories.loyalty.margin_floor_repository import (
            LoyaltyMarginFloorRepository,
        )
        repo = LoyaltyMarginFloorRepository(self._conn)
        pisos = repo.floors()
        cadenas = repo.category_chain(product_ids) if pisos else {}
        general = self._default_margin()
        resultado = {}
        for producto in product_ids:
            valor = pisos.get(("PRODUCT", str(producto)))
            if valor is None:
                for categoria in cadenas.get(str(producto), ()):
                    if ("CATEGORY", categoria) in pisos:
                        valor = pisos[("CATEGORY", categoria)]
                        break
            resultado[str(producto)] = (valor / 100) if valor is not None else general
        return resultado

    def for_sale(self, sale, *, extra_committed: Decimal = Decimal("0")) -> BenefitBudget:
        from backend.application.sales.cost_lookup import sale_unit_costs

        lineas = list(sale.goods_lines)
        costos, _sin_costo = sale_unit_costs(self._conn, sale)
        margenes = self.margins([ln.product_id for ln in lineas])
        presupuesto = [
            BudgetLine(
                product_id=ln.product_id,
                name=str((ln.product_snapshot or {}).get("name") or ln.product_id),
                revenue=ln.quantity.value * ln.unit_price,
                cost=(costos[ln.product_id] * ln.quantity.value
                      if ln.product_id in costos else None),
                min_margin=margenes.get(ln.product_id, Decimal("0.10")))
            for ln in lineas]
        t = sale.totals
        comprometido = (t.discount_total + t.promotion_total + t.coupon_total
                        + t.loyalty_total + Decimal(str(extra_committed)))
        return BenefitBudgetPolicy.compute(presupuesto, committed=comprometido)

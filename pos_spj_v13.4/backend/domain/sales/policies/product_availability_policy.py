"""ProductAvailabilityPolicy — resolves a catalog product's stock badge and
sellability server-side (master prompt §16: "No calcular el estado en el
widget a partir de floats crudos. Debe venir resuelto por QueryService.").

Ports the exact threshold logic that today lives inline inside
`modulos/ventas.py::ProductCard.__init__` (out-of-stock ≤0, critical ≤minimum,
low ≤2×minimum) — same real thresholds, not invented ones — into a pure,
testable, Decimal-only policy. `is_sellable()` adds one real improvement the
widget never had: a composite/bundle product (built from components at
checkout time, `bundle_allowed`/`recipe_allowed`) can still be added to cart
even at OUT_OF_STOCK raw quantity, since it isn't sold from its own stock row.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.sales.enums import ProductStockState


class ProductAvailabilityPolicy:
    @staticmethod
    def classify(
        available_quantity: Decimal, minimum_quantity: Decimal, *,
        sellable_override: bool = True,
    ) -> ProductStockState:
        if not sellable_override:
            return ProductStockState.NOT_SELLABLE
        if available_quantity <= 0:
            return ProductStockState.OUT_OF_STOCK
        if minimum_quantity > 0 and available_quantity <= minimum_quantity:
            return ProductStockState.CRITICAL_STOCK
        if minimum_quantity > 0 and available_quantity <= minimum_quantity * 2:
            return ProductStockState.LOW_STOCK
        return ProductStockState.AVAILABLE

    @staticmethod
    def is_sellable(state: ProductStockState, *, is_composite: bool = False) -> bool:
        if state is ProductStockState.NOT_SELLABLE:
            return False
        if state is ProductStockState.OUT_OF_STOCK and not is_composite:
            return False
        return True

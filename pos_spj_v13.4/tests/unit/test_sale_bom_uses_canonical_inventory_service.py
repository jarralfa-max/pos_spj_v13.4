from __future__ import annotations

from types import SimpleNamespace

from core.events.handlers.inventory_handler import SaleInventoryHandler


class InventorySpy:
    def __init__(self):
        self.calls = []

    def decrease_stock(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(success=True)

    def deduct_stock(self, **_kwargs):  # pragma: no cover
        raise AssertionError("deduct_stock must not be used for BOM")


def test_bom_components_use_decrease_stock_and_are_merged(monkeypatch) -> None:
    import core.services.recipes.recipe_resolver as resolver_mod

    class Line:
        def __init__(self, product_id, quantity):
            self.product_id = product_id
            self.quantity = quantity
            self.is_virtual = False

    class Explosion:
        cycle_detected = False
        deductions = [Line(20, 1.5), Line(20, 2.5)]

    class FakeResolver:
        def __init__(self, db):
            self.db = db

        def resolve_for_sale(self, product_id, sale_qty, branch_id):
            return Explosion()

    monkeypatch.setattr(resolver_mod, "RecipeResolver", FakeResolver)
    inv = InventorySpy()

    SaleInventoryHandler(inv, db=object()).handle({
        "branch_id": 1,
        "operation_id": "op-sale",
        "sale_id": "100",
        "user": "ana",
        "items": [{"product_id": 7, "qty": 2, "es_compuesto": 1}],
    })

    assert len(inv.calls) == 1
    assert inv.calls[0]["product_id"] == 20
    assert inv.calls[0]["quantity"] == 4.0
    assert inv.calls[0]["reference_type"] == "SALE_BOM"

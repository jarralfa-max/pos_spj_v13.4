from __future__ import annotations

from types import SimpleNamespace

from core.events.handlers.inventory_handler import SaleInventoryHandler


class InventorySpy:
    def __init__(self):
        self.calls = []

    def decrease_stock(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(success=True)


def test_duplicate_simple_product_lines_are_merged_before_decrease_stock() -> None:
    inv = InventorySpy()
    SaleInventoryHandler(inv).handle({
        "branch_id": 1,
        "operation_id": "op-sale",
        "sale_id": "100",
        "user": "ana",
        "items": [
            {"product_id": 7, "qty": 2, "es_compuesto": 0},
            {"product_id": 7, "qty": 3, "es_compuesto": 0},
        ],
    })

    assert len(inv.calls) == 1
    assert inv.calls[0]["product_id"] == 7
    assert inv.calls[0]["quantity"] == 5.0
    assert inv.calls[0]["reference_type"] == "SALE"

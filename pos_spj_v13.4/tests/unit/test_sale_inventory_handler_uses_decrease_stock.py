from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.events.handlers.inventory_handler import SaleInventoryHandler


class InventorySpy:
    def __init__(self, success: bool = True):
        self.success = success
        self.calls = []

    def decrease_stock(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(success=self.success, message="boom" if not self.success else "")

    def deduct_stock(self, **_kwargs):  # pragma: no cover - must not be called
        raise AssertionError("deduct_stock must not be used")


def test_sale_inventory_handler_uses_decrease_stock_with_canonical_arguments() -> None:
    inv = InventorySpy()
    SaleInventoryHandler(inv).handle({
        "branch_id": 2,
        "operation_id": "op-sale",
        "sale_id": "55",
        "user": "ana",
        "folio": "V-55",
        "items": [{"product_id": 7, "qty": 3, "unit": "kg", "es_compuesto": 0}],
    })

    assert inv.calls == [{
        "product_id": 7,
        "branch_id": 2,
        "quantity": 3.0,
        "unit": "kg",
        "operation_id": "op-sale",
        "source_module": "sales",
        "reference_type": "SALE",
        "reference_id": "55",
        "user_name": "ana",
        "reason": "Salida por venta V-55",
        "auto_commit": False,
    }]


def test_sale_inventory_handler_raises_when_decrease_stock_fails() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        SaleInventoryHandler(InventorySpy(success=False)).handle({
            "branch_id": 1,
            "operation_id": "op-sale",
            "sale_id": "55",
            "user": "ana",
            "items": [{"product_id": 7, "qty": 3, "es_compuesto": 0}],
        })

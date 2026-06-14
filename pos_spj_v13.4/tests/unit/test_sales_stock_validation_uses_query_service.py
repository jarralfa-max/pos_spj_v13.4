from __future__ import annotations

import pytest

from core.use_cases.venta import DatosPago, ItemCarrito, ProcesarVentaUC


class StockRecord:
    def __init__(self, quantity: float):
        self.quantity = quantity


class InventoryAppWithoutReads:
    def get_stock(self, *_args, **_kwargs):  # pragma: no cover - must not be called
        raise AssertionError("InventoryApplicationService.get_stock must not be used for sales validation")


class QueryService:
    def __init__(self, quantity: float | Exception):
        self.quantity = quantity
        self.calls = []

    def get_stock(self, product_id: int, branch_id: int):
        self.calls.append((product_id, branch_id))
        if isinstance(self.quantity, Exception):
            raise self.quantity
        return StockRecord(self.quantity)


class SalesShouldNotRun:
    def execute_sale_result(self, **_kwargs):  # pragma: no cover - must not be called on validation failures
        raise AssertionError("sale execution should be blocked by stock validation")


def _uc(query: QueryService) -> ProcesarVentaUC:
    return ProcesarVentaUC(
        sales_service=SalesShouldNotRun(),
        inventory_service=InventoryAppWithoutReads(),
        inventory_query_service=query,
    )


def test_stock_validation_uses_inventory_query_service_not_inventory_app() -> None:
    query = QueryService(1.0)
    result = _uc(query).ejecutar(
        [ItemCarrito(producto_id=10, cantidad=2, precio_unit=5, nombre="Producto")],
        DatosPago(monto_pagado=10),
        sucursal_id=1,
        usuario="tester",
    )

    assert not result.ok
    assert "Stock insuficiente" in result.error
    assert query.calls == [(10, 1)]


def test_stock_query_failure_blocks_sale() -> None:
    result = _uc(QueryService(RuntimeError("inventory query down"))).ejecutar(
        [ItemCarrito(producto_id=10, cantidad=1, precio_unit=5, nombre="Producto")],
        DatosPago(monto_pagado=5),
        sucursal_id=1,
        usuario="tester",
    )

    assert not result.ok
    assert "No se pudo validar stock" in result.error
    assert "inventory query down" in result.error

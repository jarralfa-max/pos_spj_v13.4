from types import SimpleNamespace

from core.use_cases.venta import ProcesarVentaUC, ItemCarrito, DatosPago


class _Inv:
    def __init__(self, stock=999):
        self.stock = stock

    def get_stock(self, producto_id, sucursal_id):
        return self.stock


class _Sales:
    def __init__(self):
        self.db = SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchone=lambda: [123]))

    def execute_sale(self, **kwargs):
        return ("F-UC", "<html></html>")


def _uc(stock=999):
    return ProcesarVentaUC(
        sales_service=_Sales(),
        inventory_service=_Inv(stock=stock),
        finance_service=None,
        loyalty_service=None,
        ticket_engine=None,
    )


def test_procesar_venta_efectivo_ok():
    uc = _uc()
    r = uc.ejecutar(
        items=[ItemCarrito(producto_id=1, cantidad=1, precio_unit=100.0, nombre="P")],
        datos_pago=DatosPago(forma_pago="Efectivo", monto_pagado=100.0),
        sucursal_id=1,
        usuario="u",
    )
    assert r.ok is True


def test_procesar_venta_credito_ok():
    uc = _uc()
    r = uc.ejecutar(
        items=[ItemCarrito(producto_id=1, cantidad=1, precio_unit=100.0, nombre="P")],
        datos_pago=DatosPago(forma_pago="Crédito", monto_pagado=100.0, cliente_id=3),
        sucursal_id=1,
        usuario="u",
    )
    assert r.ok is True


def test_procesar_venta_con_puntos_ok():
    uc = _uc()
    r = uc.ejecutar(
        items=[ItemCarrito(producto_id=1, cantidad=1, precio_unit=100.0, nombre="P")],
        datos_pago=DatosPago(forma_pago="Efectivo", monto_pagado=100.0, puntos_canjeados=10),
        sucursal_id=1,
        usuario="u",
    )
    assert r.ok is True


def test_procesar_venta_stock_insuficiente():
    uc = _uc(stock=0)
    r = uc.ejecutar(
        items=[ItemCarrito(producto_id=1, cantidad=1, precio_unit=100.0, nombre="P")],
        datos_pago=DatosPago(forma_pago="Efectivo", monto_pagado=100.0),
        sucursal_id=1,
        usuario="u",
    )
    assert r.ok is False
    assert "Stock insuficiente" in r.error

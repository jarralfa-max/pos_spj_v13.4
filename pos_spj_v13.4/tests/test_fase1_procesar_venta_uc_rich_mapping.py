from types import SimpleNamespace

from core.use_cases.venta import ProcesarVentaUC, ItemCarrito, DatosPago


class _Inv:
    def get_stock(self, producto_id, sucursal_id):
        return 999


class _Loyalty:
    enabled = True

    def __init__(self, saldo_val=777):
        self._saldo = saldo_val

    def saldo(self, cliente_id):
        return self._saldo


class _SalesRich:
    def execute_sale_result(self, **kwargs):
        return SimpleNamespace(
            venta_id=101,
            folio="V-101",
            total=321.5,
            ticket_html="<html></html>",
            operation_id="op-101",
            ticket_payload={"venta_id": 101, "folio": "V-101"},
            payment=SimpleNamespace(method="Crédito", amount_paid=321.5, change=0.0, breakdown={"credito": 321.5}),
            loyalty=SimpleNamespace(
                cliente_id=kwargs.get("client_id"),
                puntos_canjeados=10,
                descuento_puntos=5.0,
                puntos_ganados=12,
                puntos_totales=222,
                nivel="Oro",
                mensaje="ok",
                operation_id="op-101",
                available=True,
            ),
            warnings=["w1"],
        )


class _SalesLegacy:
    def __init__(self):
        self.db = SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchone=lambda: (555,)))

    def execute_sale(self, **kwargs):
        return ("F-LEG", "<html>legacy</html>")


def _uc(sales, loyalty=None):
    return ProcesarVentaUC(sales, _Inv(), None, loyalty or _Loyalty(), None)


def _items():
    return [ItemCarrito(producto_id=1, cantidad=1, precio_unit=100.0, nombre="Pollo")]


def _dp(cliente_id=1):
    return DatosPago(forma_pago="Efectivo", monto_pagado=100.0, cliente_id=cliente_id)


def test_uc_maps_sale_execution_result_operation_id():
    r = _uc(_SalesRich()).ejecutar(_items(), _dp(), 1, "cajero")
    assert r.operation_id == "op-101"


def test_uc_maps_sale_execution_result_ticket_payload():
    r = _uc(_SalesRich()).ejecutar(_items(), _dp(), 1, "cajero")
    assert r.ticket_payload.get("venta_id") == 101


def test_uc_maps_sale_execution_result_payment():
    r = _uc(_SalesRich()).ejecutar(_items(), _dp(), 1, "cajero")
    assert r.payment_breakdown.get("breakdown", {}).get("credito") == 321.5


def test_uc_maps_sale_execution_result_loyalty():
    r = _uc(_SalesRich()).ejecutar(_items(), _dp(), 1, "cajero")
    assert r.loyalty_result.get("puntos_totales") == 222


def test_uc_no_returns_fake_zero_points_when_rich_has_loyalty():
    r = _uc(_SalesRich()).ejecutar(_items(), _dp(), 1, "cajero")
    assert r.puntos_ganados == 12
    assert r.puntos_totales == 222
    assert r.nivel_cliente == "Oro"


def test_uc_legacy_route_is_blocked_without_ticket_fallback():
    r = _uc(_SalesLegacy()).ejecutar(_items(), _dp(), 1, "cajero")
    assert r.ok is False
    assert "execute_sale_result" in r.error
    assert r.ticket_html == ""
    assert r.ticket_payload == {}

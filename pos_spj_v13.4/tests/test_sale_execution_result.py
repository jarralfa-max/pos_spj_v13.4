from core.services.sales.sale_execution_result import SaleExecutionResult
from core.services.sales_service import SalesService


class _DB:
    def execute(self, q, p=()):
        self._q = q
        self._p = p
        return self

    def fetchone(self):
        if "FROM ventas" in self._q:
            return (101, 100.0, 5.0, 95.0, "Efectivo", 100.0, 5.0, "op-123")
        if "FROM loyalty_cards" in self._q:
            return (220, "Oro")
        return None

    def fetchall(self):
        if "FROM detalle_ventas" in self._q:
            return [(1, "Producto A", 2.0, 10.0, 20.0, 1.0, 19.0, 0)]
        return []


class _Svc(SalesService):
    def _execute_sale_core(self, **kwargs):
        if kwargs.get("return_details"):
            return {
                "ok": True,
                "venta_id": 101,
                "folio": "FOLIO-1",
                "operation_id": "op-123",
                "subtotal": 100.0,
                "descuento_total": 5.0,
                "total": 95.0,
                "items": [{"product_id": 1, "nombre": "Producto A", "qty": 2.0, "unit_price": 10.0, "es_compuesto": 0}],
                "payment": {"forma_pago": "Efectivo", "total_pagado": 100.0, "efectivo_recibido": 100.0, "cambio": 5.0, "lineas": {"efectivo": 95.0}},
                "loyalty": {"cliente_id": kwargs.get("client_id"), "puntos_canjeados": 0, "descuento_puntos": 0.0, "puntos_ganados": 0, "puntos_totales": 220, "nivel": "Oro", "mensaje": "", "operation_id": "op-123"},
                "ticket_payload": {"folio": "FOLIO-1"},
                "ticket_html": "<html>ticket</html>",
                "warnings": [],
                "error": "",
            }
        return "FOLIO-1", "<html>ticket</html>"


def _build_svc():
    return _Svc(_DB(), None, None, None, None, None, None, None, None, None, None, None)


def test_sale_execution_result_contains_real_total():
    r = _build_svc().execute_sale_result(1, "cajero", [], "Efectivo", 100.0)
    assert isinstance(r, SaleExecutionResult)
    assert r.total == 95.0


def test_sale_execution_result_contains_real_items():
    r = _build_svc().execute_sale_result(1, "cajero", [], "Efectivo", 100.0)
    assert len(r.items) == 1
    assert r.items[0].nombre == "Producto A"


def test_sale_execution_result_contains_operation_id():
    r = _build_svc().execute_sale_result(1, "cajero", [], "Efectivo", 100.0)
    assert r.operation_id == "op-123"


def test_sale_execution_result_contains_loyalty_result():
    r = _build_svc().execute_sale_result(1, "cajero", [], "Efectivo", 100.0, client_id=7)
    assert r.loyalty is not None
    assert r.loyalty.cliente_id == 7


def test_sale_execution_result_contains_ticket_payload():
    r = _build_svc().execute_sale_result(1, "cajero", [], "Efectivo", 100.0)
    assert r.ticket_payload.get("folio") == "FOLIO-1"

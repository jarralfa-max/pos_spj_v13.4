from unittest.mock import MagicMock

from core.use_cases.venta import ProcesarVentaUC, ItemCarrito, DatosPago


def _make_uc():
    sales = MagicMock()
    sales.execute_sale.return_value = ("F-100", "<html>ticket</html>")
    sales.db = MagicMock()
    sales.db.execute.return_value.fetchone.return_value = (100,)

    inv = MagicMock()
    inv.get_stock.return_value = 999

    loyalty = MagicMock()
    sync = MagicMock()
    bus = MagicMock()

    uc = ProcesarVentaUC(
        sales_service=sales,
        inventory_service=inv,
        finance_service=MagicMock(),
        loyalty_service=loyalty,
        ticket_engine=MagicMock(),
        sync_service=sync,
        event_bus=bus,
    )
    return uc, sales, loyalty, sync, bus


def test_uc_calls_sales_service_once_and_returns_ok_resultado():
    uc, sales, loyalty, sync, bus = _make_uc()

    res = uc.ejecutar(
        items=[ItemCarrito(producto_id=1, cantidad=2, precio_unit=50.0, nombre="A")],
        datos_pago=DatosPago(forma_pago="Efectivo", monto_pagado=100.0, cliente_id=1),
        sucursal_id=1,
        usuario="cajero",
    )

    assert res.ok is True
    assert res.venta_id == 100
    assert res.folio == "F-100"
    assert res.total == 100.0
    assert res.ticket_html == "<html>ticket</html>"
    assert res.error == ""

    sales.execute_sale.assert_called_once()
    loyalty.process_loyalty_for_sale.assert_not_called()
    sync.registrar_evento.assert_not_called()
    bus.publish.assert_not_called()

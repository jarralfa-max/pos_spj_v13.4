import sqlite3
from unittest.mock import MagicMock

from services.mercado_pago_service import MercadoPagoService
from core.services.sales_service import SalesService


def test_webhook_approved_confirms_pending_sale():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE links_pago (pedido_id TEXT PRIMARY KEY, monto REAL, preference_id TEXT, url_pago TEXT, estado TEXT, payment_id TEXT, fecha_pago TEXT)")
    db.execute("INSERT INTO links_pago(pedido_id, monto, preference_id, url_pago, estado) VALUES ('VREF-1', 120.0, 'P1', 'U', 'pendiente')")
    db.commit()

    mp = MercadoPagoService(conn=db)
    mp.verificar_pago = MagicMock(return_value={
        "status": "approved",
        "external_ref": "VREF-1",
        "transaction_amount": 120.0,
    })
    mp.sales_service = MagicMock()
    mp.sales_service.confirm_pending_payment_sale.return_value = ("F-1", "")

    ok = mp.procesar_webhook({"type": "payment", "data": {"id": "123"}})
    assert ok is True
    mp.sales_service.confirm_pending_payment_sale.assert_called_once_with("VREF-1", payment_id="123")


def test_sales_service_confirm_pending_payment_sale_executes_sale_once():
    svc = SalesService(
        db_conn=MagicMock(),
        sales_repo=MagicMock(),
        recipe_repo=MagicMock(),
        inventory_service=MagicMock(),
        finance_service=MagicMock(),
        loyalty_service=MagicMock(),
        promotion_engine=None,
        sync_service=None,
        ticket_template_engine=MagicMock(),
        whatsapp_service=MagicMock(),
        config_service=MagicMock(),
        feature_flag_service=MagicMock(),
        customer_service=MagicMock(),
    )

    row = ("{\"branch_id\":1,\"user\":\"caj\",\"client_id\":1,\"items\":[{\"product_id\":1,\"qty\":1,\"unit_price\":100}],\"total\":100,\"notes\":\"x\"}", "pendiente_pago")
    svc.db.execute.return_value.fetchone.return_value = row
    svc.execute_sale = MagicMock(return_value=("F-100", "<t>"))

    folio, ticket = svc.confirm_pending_payment_sale("VREF-1", payment_id="P-1")
    assert folio == "F-100"
    assert ticket == "<t>"
    svc.execute_sale.assert_called_once()

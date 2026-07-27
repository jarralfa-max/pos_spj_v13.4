from unittest.mock import MagicMock

from core.services.loyalty_service import LoyaltyService
from core.services.sales_service import SalesService


def test_preview_redemption_does_not_write_ledger(tmp_path):
    import sqlite3
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE clientes(id INTEGER PRIMARY KEY, puntos INTEGER DEFAULT 0)")
    db.execute("INSERT INTO clientes(id,puntos) VALUES(1,100)")
    db.execute("CREATE TABLE loyalty_ledger(id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, referencia TEXT, puntos INTEGER, monto_equiv REAL, saldo_post INTEGER, descripcion TEXT, sucursal_id TEXT, usuario TEXT)")
    svc = LoyaltyService(db_conn=db)
    svc.preview_redemption(cliente_id=1, subtotal=200.0)
    c = db.execute("SELECT COUNT(*) FROM loyalty_ledger").fetchone()[0]
    assert c == 0


def test_apply_redemption_idempotent_by_venta_id():
    svc = MagicMock()
    svc.compute_redemption_discount.return_value = 10.0
    svc.apply_redemption.return_value = {"ok": True}

    sales_repo = MagicMock()
    sales_repo.create_sale.return_value = (10, "F-10")
    sales_repo.save_sale_item.return_value = None

    db = MagicMock()
    db.cursor.return_value = MagicMock()

    ss = SalesService(
        db_conn=db,
        sales_repo=sales_repo,
        recipe_repo=MagicMock(),
        inventory_service=MagicMock(),
        finance_service=MagicMock(),
        loyalty_service=svc,
        promotion_engine=None,
        sync_service=None,
        ticket_template_engine=MagicMock(),
        whatsapp_service=None,
        config_service=MagicMock(get=MagicMock(return_value="")),
        feature_flag_service=MagicMock(),
        customer_service=MagicMock(get_customer=MagicMock(return_value={"id": 1}), validate_credit=MagicMock(return_value=(True, ""))),
    )
    ss._validate_stock_pre_sale = MagicMock()
    ss._resolve_sale_items = MagicMock(return_value=[])

    from core.events import event_bus
    bus = event_bus.get_bus()
    original = bus.publish
    bus.publish = MagicMock(return_value=None)
    try:
        ss.execute_sale(
            branch_id=1,
            user="cajero",
            items=[{"product_id": 1, "qty": 1, "unit_price": 100}],
            payment_method="Efectivo",
            amount_paid=100,
            client_id=1,
            loyalty_redemption_pts=20,
        )
    finally:
        bus.publish = original

    svc.apply_redemption.assert_called_once()
    kwargs = svc.apply_redemption.call_args.kwargs
    assert kwargs["venta_id"] == 10
    assert kwargs["puntos"] == 20

from pathlib import Path
import sqlite3

from core.services.sales_service import SalesService

SALES_SRC = (Path(__file__).resolve().parents[1] / "core" / "services" / "sales_service.py").read_text(encoding="utf-8")


def _service_with_stock(stock=5.0):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE branch_inventory(branch_id INTEGER, product_id INTEGER, quantity REAL)")
    db.execute(
        "INSERT INTO branch_inventory(branch_id, product_id, quantity) VALUES(1,1,?)",
        (float(stock),),
    )
    svc = SalesService.__new__(SalesService)
    svc.db = db
    return svc, db


# modulos/ventas.py (legacy) retirado (SALES-22) — las 4 pruebas que leían su
# código fuente directamente (reenables_cobrar_button/does_not_leave_checkout_
# running_true/mp_link_failure_releases_pending_reservation/has_recoverable_
# context) se retiraron con él. Las de abajo prueban SalesService directamente
# y no dependen de ese archivo.


def test_mp_pending_creates_reservation():
    svc, db = _service_with_stock(stock=5.0)
    pending = svc.create_pending_payment_sale(
        branch_id=1,
        user="u",
        items=[{"product_id": 1, "qty": 2, "unit_price": 10}],
        client_id=None,
        total=20.0,
    )
    assert pending["estado"] == "pendiente_pago"
    assert pending["reservation_id"] > 0
    estado = db.execute(
        "SELECT estado FROM stock_reservas WHERE id=?",
        (pending["reservation_id"],),
    ).fetchone()[0]
    assert estado == "activa"
    intent = db.execute(
        "SELECT estado, reservation_id FROM pending_sales_intents WHERE folio=?",
        (pending["folio"],),
    ).fetchone()
    assert intent["estado"] == "pendiente_pago"
    assert int(intent["reservation_id"]) == pending["reservation_id"]


def test_mp_pending_cancel_releases_reservation():
    svc, db = _service_with_stock(stock=5.0)
    pending = svc.create_pending_payment_sale(
        branch_id=1,
        user="u",
        items=[{"product_id": 1, "qty": 1, "unit_price": 10}],
        total=10.0,
    )
    svc.cancel_pending_payment_sale(pending["folio"], motivo="cancelada")
    reserva_estado = db.execute(
        "SELECT estado FROM stock_reservas WHERE id=?",
        (pending["reservation_id"],),
    ).fetchone()[0]
    intent_estado = db.execute(
        "SELECT estado FROM pending_sales_intents WHERE folio=?",
        (pending["folio"],),
    ).fetchone()[0]
    assert reserva_estado == "cancelada"
    assert intent_estado == "cancelada"


def test_mp_pending_confirm_uses_reserved_stock():
    # UUIDv7 identity (REGLA CERO): reservation_id flows through as TEXT, never int()-cast.
    assert "reservation_id = data.get(\"reservation_id\") or None" in SALES_SRC
    assert "payment_breakdown={\"mercado_pago\": total}" in SALES_SRC
    assert "reservation_id=reservation_id" in SALES_SRC

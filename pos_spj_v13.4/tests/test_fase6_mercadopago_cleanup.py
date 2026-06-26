from pathlib import Path
import sqlite3

from core.services.sales_service import SalesService

SRC = (Path(__file__).resolve().parents[1] / "modulos" / "ventas.py").read_text(encoding="utf-8")
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


def test_mp_pending_reenables_cobrar_button():
    assert "finally:" in SRC
    assert "_worker_started" not in SRC
    assert "self._on_checkout_finished()" in SRC


def test_mp_pending_does_not_leave_checkout_running_true():
    assert "self._venta_checkout_running = False" in SRC


def test_mp_link_failure_releases_pending_reservation_before_raising():
    start = SRC.find("if is_mercado_pago(datos_pago.get('forma_pago')):")
    end = SRC.find("# ── Guardrail: detectar ítems por debajo del costo", start)
    block = SRC[start:end]
    assert 'sales_svc.cancel_pending_payment_sale(folio_pend, motivo="link_failed")' in block
    assert "raise RuntimeError(\"No se pudo generar link de pago MercadoPago.\")" in block
    fail_idx = block.find("raise RuntimeError(\"No se pudo generar link de pago MercadoPago.\")")
    clear_idx = block.find("self.cancelar_venta(silent=True)")
    assert clear_idx == -1 or clear_idx > fail_idx


def test_mp_pending_has_recoverable_context():
    assert '"estado": "pendiente_pago"' in SRC
    assert '"folio": folio_pend' in SRC
    assert '"reservation_id": pending.get("reservation_id")' in SRC
    assert '"compra": list(self.compra_actual)' in SRC
    assert '"totales": dict(self.totales)' in SRC
    assert '"datos_pago": dict(datos_pago or {})' in SRC


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

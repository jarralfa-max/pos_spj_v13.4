import sqlite3

from core.services.sales.sale_loyalty_policy import SaleLoyaltyPolicy


class _LoyaltyStub:
    def preview_redemption(self, **kwargs):
        return {"ok": True, "descuento": 10.0}

    def apply_redemption(self, **kwargs):
        return {"ok": True}

    def process_loyalty_for_sale(self, **kwargs):
        return {"puntos_ganados": 5, "puntos_totales": 15, "nivel": "Bronce"}


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE clientes(id INTEGER PRIMARY KEY, puntos INTEGER)")
    db.execute("CREATE TABLE historico_puntos(cliente_id INTEGER, tipo TEXT, puntos INTEGER, descripcion TEXT, saldo_actual INTEGER, usuario TEXT, venta_id INTEGER)")
    db.execute("INSERT INTO clientes(id,puntos) VALUES(1,20)")
    return db


def test_preview_apply_earn_reverse_idempotent():
    db = _db()
    p = SaleLoyaltyPolicy(db, loyalty_service=_LoyaltyStub())

    prev = p.preview_redemption(cliente_id=1, puntos=10, subtotal=100)
    assert prev["ok"] is True

    a1 = p.apply_redemption(cliente_id=1, venta_id=10, puntos=10, operation_id="op:r")
    a2 = p.apply_redemption(cliente_id=1, venta_id=10, puntos=10, operation_id="op:r")
    assert a1["ok"] is True
    assert a2.get("idempotent") is True

    e1 = p.earn_points(cliente_id=1, venta_id=10, total=200, operation_id="op:e")
    e2 = p.earn_points(cliente_id=1, venta_id=10, total=200, operation_id="op:e")
    assert e1["ok"] is True
    assert e2.get("idempotent") is True

    r1 = p.reverse_points(cliente_id=1, venta_id=10, operation_id="op:v", puntos=5, usuario="u")
    r2 = p.reverse_points(cliente_id=1, venta_id=10, operation_id="op:v", puntos=5, usuario="u")
    assert r1["ok"] is True
    assert r2.get("idempotent") is True

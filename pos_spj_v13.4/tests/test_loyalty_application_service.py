import sqlite3

from application.services.loyalty_application_service import LoyaltyApplicationService


def _db():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE loyalty_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, tipo TEXT, puntos INTEGER, monto_equiv REAL DEFAULT 0, saldo_post INTEGER DEFAULT 0, referencia TEXT DEFAULT '', descripcion TEXT DEFAULT '', sucursal_id INTEGER DEFAULT 1, usuario TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')), UNIQUE(cliente_id,tipo,referencia))")
    db.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, puntos INTEGER DEFAULT 0)")
    db.execute("INSERT INTO clientes(id,nombre,puntos) VALUES (1,'A',0)")
    return db


def test_acumulacion_unica_por_venta():
    db = _db()
    svc = LoyaltyApplicationService(db)
    r1 = svc.award_points_for_sale(cliente_id=1, venta_id='V1', puntos=10)
    r2 = svc.award_points_for_sale(cliente_id=1, venta_id='V1', puntos=10)
    assert r1['ok'] is True
    assert r2['idempotent'] is True


def test_canje_y_reversa():
    db = _db()
    svc = LoyaltyApplicationService(db)
    svc.award_points_for_sale(cliente_id=1, venta_id='V1', puntos=100)
    red = svc.redeem_points_for_sale(cliente_id=1, venta_id='V2', puntos=50)
    rev = svc.reverse_redemption(cliente_id=1, venta_id='V2', puntos=50)
    assert red['ok'] is True
    assert rev['ok'] is True
    assert svc.get_customer_loyalty_summary(cliente_id=1)['saldo_ledger'] == 100

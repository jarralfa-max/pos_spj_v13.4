import py_compile
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from application.services.loyalty_application_service import LoyaltyApplicationService
from core.events.event_bus import EventBus, VENTA_COMPLETADA
from core.events.wiring import _wire_venta
from core.services.loyalty_service import LoyaltyService

ROOT = Path(__file__).resolve().parents[1]


def _db_basic():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, puntos INTEGER, monto_equiv REAL DEFAULT 0, saldo_post INTEGER DEFAULT 0, referencia TEXT DEFAULT '', descripcion TEXT DEFAULT '', sucursal_id TEXT, usuario TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')), UNIQUE(cliente_id,tipo,referencia))")
    db.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, puntos INTEGER DEFAULT 0)")
    db.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    db.execute("CREATE TABLE loyalty_pasivo_log (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, tipo TEXT, estrellas INTEGER, valor_unitario REAL, monto_total REAL, referencia TEXT, sucursal_id INTEGER)")
    db.execute("INSERT INTO clientes(id,nombre,puntos) VALUES (1,'Ana',0)")
    return db


def test_award_points_idempotent():
    db = _db_basic()
    svc = LoyaltyApplicationService(db)
    svc.award_points_for_sale(cliente_id=1, venta_id='V-AWARD-1', puntos=20)
    svc.award_points_for_sale(cliente_id=1, venta_id='V-AWARD-1', puntos=20)
    count = db.execute("SELECT COUNT(*) FROM loyalty_ledger WHERE cliente_id=1 AND tipo='acumulacion' AND referencia='V-AWARD-1'").fetchone()[0]
    saldo = db.execute("SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger WHERE cliente_id=1").fetchone()[0]
    assert count == 1
    assert saldo == 20


def test_redeem_points_idempotent():
    db = _db_basic()
    svc = LoyaltyApplicationService(db)
    svc.award_points_for_sale(cliente_id=1, venta_id='V-BASE-1', puntos=100)
    svc.redeem_points_for_sale(cliente_id=1, venta_id='V-RED-1', puntos=30)
    svc.redeem_points_for_sale(cliente_id=1, venta_id='V-RED-1', puntos=30)
    count = db.execute("SELECT COUNT(*) FROM loyalty_ledger WHERE cliente_id=1 AND tipo='canje' AND referencia='V-RED-1'").fetchone()[0]
    saldo = db.execute("SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger WHERE cliente_id=1").fetchone()[0]
    assert count == 1
    assert saldo == 70


def test_birthday_config_does_not_touch_referrals():
    db = _db_basic()
    ls = LoyaltyService(db)
    ls.save_referral_config(60, 30, 9)
    ls.save_birthday_config(123, 'Hola {nombre}')
    bday = ls.get_birthday_config()
    ref = ls.get_referral_config()
    assert bday['cumple_bono_estrellas'] == '123'
    assert bday['cumple_mensaje_wa'] == 'Hola {nombre}'
    assert ref['ref_bono_referidor'] == 60
    assert ref['ref_bono_referido'] == 30
    assert ref['ref_max_mensual'] == 9


def test_no_private_repo_access_in_fidelidad_ui():
    src = (ROOT / 'modulos' / 'fidelidad_config.py').read_text(encoding='utf-8')
    assert '_app.repo' not in src
    assert 'db.execute' not in src


def test_growth_engine_ui_py_compile():
    py_compile.compile(str(ROOT / 'modulos' / 'modulo_growth_engine.py'), doraise=True)


def test_venta_completada_skip_loyalty_if_already_processed():
    db = _db_basic()
    container = type('C', (), {})()
    container.db = db
    container.sync_service = None
    container.loyalty_service = MagicMock()
    container.finance_service = None
    bus = EventBus()
    bus.clear_handlers()
    _wire_venta(bus, container)
    bus.publish(VENTA_COMPLETADA, {
        'cliente_id': 1,
        'total': 100,
        'venta_id': 1,
        'sucursal_id': 1,
        'usuario': 'u',
        'loyalty_already_processed': True,
    }, async_=False)
    container.loyalty_service.process_loyalty_for_sale.assert_not_called()
